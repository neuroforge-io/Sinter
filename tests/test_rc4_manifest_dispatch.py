"""Bounded discovery controls only; no installed run or release is qualified."""

from __future__ import annotations

import json
import os

import pytest

from tools import candidate_qualification as legacy
from tools import candidate_release as dispatch
from tools import rc4_candidate_release as rc4
from tools import release_tag

COMMIT = "a" * 40
OLD_LIMIT = 2 * 1024 * 1024


def profile():
    return {
        "schema": rc4.SCHEMA,
        "version": rc4.VERSION,
        "source_commit": COMMIT,
        "repository": legacy.REPOSITORY,
        "tag": "v" + rc4.VERSION,
        "prerelease": True,
        "latest": False,
        "qualified_targets": [legacy.TARGET],
        "unqualified_targets": legacy.UNQUALIFIED,
        "all_platform_release_qualified": False,
        "publication_executed": False,
        "original_authorization_required": True,
        "historical_semantic_replay": False,
        "new_installed_execution": False,
        "assets": [],
        "source_only_inert_dispatch_control": True,
    }


def document(tmp_path, value, *, size=None):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if size is not None:
        assert len(raw) <= size
        raw += b" " * (size - len(raw))
    path = tmp_path / "candidate-release-manifest.json"
    path.write_bytes(raw)
    return path


def inert_original(monkeypatch, plan):
    observed = []

    def original(path, **kwargs):
        observed.append((path, kwargs))
        return plan

    monkeypatch.setattr(rc4, "authorize_original", original)
    monkeypatch.setattr(
        release_tag,
        "_api",
        lambda *args, **kwargs: pytest.fail("No tag/network action is authorised"),
    )
    return observed


def external_inputs(tmp_path, monkeypatch, path):
    # Typed context/pins are inert test markers; no external record grants proof.
    context, pins = object(), object()
    observed = []

    def load(*args):
        observed.append(args)
        return context, pins

    monkeypatch.setattr(rc4, "load_original", load)
    files = {
        "original-context": tmp_path / "context.json",
        "original-context-sha256": "b" * 64,
        "trusted-pins": tmp_path / "pins.json",
        "trusted-pins-sha256": "c" * 64,
        "manifest-sha256": rc4.sha(path.read_bytes()),
    }
    return context, pins, files, observed


@pytest.mark.parametrize("size", [OLD_LIMIT + 1, 4_059_599, rc4.MAX_FILE])
def test_rc4_finite_manifest_reaches_fixed_original_gate(tmp_path, monkeypatch, size):
    plan = profile()
    plan["source_only_unicode_control"] = "e\u0301 🐝"
    path = document(tmp_path, plan, size=size)
    observed = inert_original(monkeypatch, plan)
    context, pins, files, _loads = external_inputs(tmp_path, monkeypatch, path)
    assert (
        dispatch.verify_plan(
            path,
            rc4_context=context,
            rc4_pins=pins,
            rc4_manifest_sha256=files["manifest-sha256"],
        )
        is plan
    )
    assert observed == [
        (
            path,
            {
                "context": context,
                "pins": pins,
                "manifest_sha256": files["manifest-sha256"],
            },
        )
    ]
    assert rc4.MAX_FILE == 64 * 1024 * 1024
    assert rc4.MAX_BUNDLE == 256 * 1024 * 1024


@pytest.mark.parametrize("operation", ["verify", "commands", "tag-identity"])
def test_large_manifest_cli_and_tag_use_same_discovery(
    tmp_path, monkeypatch, capsys, operation
):
    plan = profile()
    path = document(tmp_path, plan, size=4_059_599)
    observed = inert_original(monkeypatch, plan)
    context, pins, files, loads = external_inputs(tmp_path, monkeypatch, path)
    if operation == "tag-identity":
        release_tag._candidate_identity(
            path,
            legacy.REPOSITORY,
            "v" + rc4.VERSION,
            COMMIT,
            **{key.replace("-", "_"): value for key, value in files.items()},
        )
        assert len(loads) == 1
    else:
        argv = [operation, str(path)]
        for key, value in files.items():
            argv.extend(["--" + key, str(value)])
        dispatch.main(argv)
        output = capsys.readouterr().out
        assert rc4.VERSION in output
        assert len(loads) == (2 if operation == "commands" else 1)
        if operation == "commands":
            assert "--manifest-sha256" in output and "--trusted-pins" in output
    assert len(observed) == 1
    assert observed[0][1] == {
        "context": context,
        "pins": pins,
        "manifest_sha256": files["manifest-sha256"],
    }


@pytest.mark.parametrize("version", ["0.5.4rc1", "0.5.4rc2", "0.5.4rc3"])
@pytest.mark.parametrize("size", [OLD_LIMIT, OLD_LIMIT + 1, 4_059_599])
def test_legacy_exact_2mib_boundary_remains_authoritative(
    tmp_path, monkeypatch, version, size
):
    path = document(tmp_path, {"version": version}, size=size)
    observed = inert_original(monkeypatch, profile())
    if size == OLD_LIMIT:
        assert dispatch._manifest_for_dispatch(path) == {"version": version}
    else:
        with pytest.raises(ValueError, match="An evidence document exceeds its bound"):
            dispatch._manifest_for_dispatch(path)
        with pytest.raises(ValueError, match="An evidence document exceeds its bound"):
            legacy._json(path)
    assert observed == []


PROFILE_FIELDS = tuple(
    key
    for key in profile()
    if key not in {"assets", "source_only_inert_dispatch_control"}
)


@pytest.mark.parametrize("field", PROFILE_FIELDS)
@pytest.mark.parametrize("mutation", ["missing", "contradictory"])
def test_missing_or_contradictory_profile_cannot_select_original_authority(
    tmp_path, monkeypatch, field, mutation
):
    plan = profile()
    if mutation == "missing":
        del plan[field]
    else:
        plan[field] = {"fake": "0.5.4rc4"}
    path = document(tmp_path, plan, size=OLD_LIMIT + 1)
    observed = inert_original(monkeypatch, plan)
    with pytest.raises(ValueError):
        dispatch.verify_plan(path, rc4_context="inert", rc4_pins="inert")
    assert observed == []


@pytest.mark.parametrize(
    "value",
    [
        {"nested": profile()},
        {"version": "0.5.4rc4.dev0", "nested": profile()},
        {"version": "0.5.4rc40", "nested": profile()},
        {"version": ["0.5.4rc4"], "nested": profile()},
        {"version": " 0.5.4rc4", "nested": profile()},
        {"version": "0.5.4rc4\u0000", "nested": profile()},
        {"version": "0.5.4rc４", "nested": profile()},
        {"version": "0.5.4rc3", "schema": rc4.SCHEMA, "nested": profile()},
    ],
)
def test_nested_or_fake_version_never_routes_rc4(tmp_path, monkeypatch, value):
    path = document(tmp_path, value, size=OLD_LIMIT + 1)
    observed = inert_original(monkeypatch, profile())
    with pytest.raises(ValueError, match="An evidence document exceeds its bound"):
        dispatch.verify_plan(path, rc4_context="inert", rc4_pins="inert")
    assert observed == []


@pytest.mark.parametrize(
    "tail",
    [
        '"version":"0.5.4rc4"',
        '"version":"0.5.4rc3"',
        '"schema":"fake"',
        '"latest":true',
        '"nested":{"same":1,"same":2}',
    ],
)
@pytest.mark.parametrize("large", [False, True])
def test_duplicate_fields_refuse_before_fixed_gate(tmp_path, monkeypatch, tail, large):
    raw = rc4.canonical(profile()).rstrip()[:-1] + b"," + tail.encode() + b"}"
    if large:
        raw += b" " * OLD_LIMIT
    path = tmp_path / "candidate-release-manifest.json"
    path.write_bytes(raw)
    observed = inert_original(monkeypatch, profile())
    with pytest.raises(ValueError, match="duplicate JSON field"):
        dispatch.verify_plan(path, rc4_context="inert", rc4_pins="inert")
    assert observed == []


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"{} trailing",
        b"[]",
        b'{"version":"0.5.4rc4",}',
        b'{"version":"0.5.4rc4","source_commit":"\xff"}',
        b'{"version":"0.5.4rc4","source_commit":"\xed\xa0\x80"}',
        b'{"version":"0.5.4rc4","source_commit":"\\ud800"}',
        b"[" * 1500 + b"]" * 1500,
    ],
)
@pytest.mark.parametrize("large", [False, True])
def test_malformed_json_utf8_unicode_cannot_reach_authority(
    tmp_path, monkeypatch, raw, large
):
    if large:
        raw += b" " * OLD_LIMIT
    path = tmp_path / "candidate-release-manifest.json"
    path.write_bytes(raw)
    observed = inert_original(monkeypatch, profile())
    with pytest.raises(ValueError):
        dispatch.verify_plan(path, rc4_context="inert", rc4_pins="inert")
    assert observed == []


@pytest.mark.parametrize("version", [rc4.VERSION, "0.5.4rc3", "fake"])
def test_above_member_bound_refuses_before_json_or_gate(tmp_path, monkeypatch, version):
    path = document(tmp_path, {"version": version})
    with path.open("r+b") as stream:
        stream.truncate(rc4.MAX_FILE + 1)
    observed = inert_original(monkeypatch, profile())
    monkeypatch.setattr(
        dispatch.json,
        "loads",
        lambda *args, **kwargs: pytest.fail("Oversized JSON was parsed"),
    )
    with pytest.raises(ValueError, match="exceeds discovery bound"):
        dispatch.verify_plan(path)
    assert observed == []


def test_discovery_success_without_original_pins_is_not_authority(tmp_path):
    path = document(tmp_path, profile(), size=4_059_599)
    with pytest.raises(ValueError, match="Independent product/source pins"):
        dispatch.verify_plan(path)


@pytest.mark.parametrize("operation", ["verify", "commands"])
def test_cli_large_rc4_requires_explicit_external_inputs(tmp_path, capsys, operation):
    path = document(tmp_path, profile(), size=4_059_599)
    with pytest.raises(SystemExit) as error:
        dispatch.main([operation, str(path)])
    assert error.value.code == 1
    assert "RC4 requires explicit original context" in capsys.readouterr().err


def test_tag_missing_authorization_refuses_before_any_network(tmp_path, monkeypatch):
    path = document(tmp_path, profile(), size=4_059_599)
    observed = inert_original(monkeypatch, profile())
    with pytest.raises(ValueError, match="RC4 tags require"):
        release_tag.ensure_release_tag(
            legacy.REPOSITORY, "v" + rc4.VERSION, COMMIT, path
        )
    assert observed == []


def test_discovery_changed_file_refuses_and_closes_descriptor(tmp_path, monkeypatch):
    path = document(tmp_path, profile())
    read, close = dispatch.os.read, dispatch.os.close
    reads, closes = [], []

    def changed_read(descriptor, size):
        result = read(descriptor, size)
        reads.append(descriptor)
        if len(reads) == 1:
            with path.open("ab") as stream:
                stream.write(b" ")
        return result

    def observed_close(descriptor):
        closes.append(descriptor)
        return close(descriptor)

    monkeypatch.setattr(dispatch.os, "read", changed_read)
    monkeypatch.setattr(dispatch.os, "close", observed_close)
    with pytest.raises(ValueError, match="changed during discovery"):
        dispatch._manifest_for_dispatch(path)
    assert len(closes) == 1 and closes[0] == reads[0]


@pytest.mark.skipif(os.name != "posix", reason="Actual POSIX symlink/FIFO unavailable")
@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_special_manifest_refuses_before_open(tmp_path, monkeypatch, kind):
    path = tmp_path / "candidate-release-manifest.json"
    if kind == "fifo":
        os.mkfifo(path)
    else:
        target = tmp_path / "target.json"
        target.write_bytes(rc4.canonical(profile()))
        path.symlink_to(target)
    monkeypatch.setattr(
        dispatch.os, "open", lambda *args, **kwargs: pytest.fail("Special path opened")
    )
    with pytest.raises(ValueError, match="special"):
        dispatch._manifest_for_dispatch(path)


def test_exact_source_commit_type_is_required(tmp_path, monkeypatch):
    plan = profile()
    plan["source_commit"] = int("1" * 40)
    path = document(tmp_path, plan)
    observed = inert_original(monkeypatch, plan)
    with pytest.raises(ValueError, match="identity/profile"):
        dispatch.verify_plan(path)
    assert observed == []


@pytest.mark.parametrize(
    "field",
    [
        "prerelease",
        "latest",
        "all_platform_release_qualified",
        "publication_executed",
        "original_authorization_required",
        "historical_semantic_replay",
        "new_installed_execution",
    ],
)
@pytest.mark.parametrize("value", [0, 1])
def test_truthy_numbers_cannot_replace_exact_profile_booleans(
    tmp_path, monkeypatch, field, value
):
    plan = profile()
    plan[field] = value
    path = document(tmp_path, plan)
    observed = inert_original(monkeypatch, plan)
    with pytest.raises(ValueError, match="identity/profile"):
        dispatch.verify_plan(path)
    assert observed == []


@pytest.mark.parametrize("targets", [[], [legacy.TARGET, "windows-x64"], "linux-x64"])
def test_other_target_profiles_cannot_select_rc4(tmp_path, monkeypatch, targets):
    plan = profile()
    plan["qualified_targets"] = targets
    path = document(tmp_path, plan)
    observed = inert_original(monkeypatch, plan)
    with pytest.raises(ValueError, match="identity/profile"):
        dispatch.verify_plan(path)
    assert observed == []


def test_discovery_preserves_first_fault_when_descriptor_cleanup_fails(
    tmp_path, monkeypatch
):
    path = document(tmp_path, profile())
    first = OSError("First actual discovery read fault")
    cleanup = OSError("Later descriptor-close diagnostic")
    close = dispatch.os.close

    def close_and_fail(descriptor):
        close(descriptor)
        raise cleanup

    def read_fault(*args):
        raise first

    monkeypatch.setattr(dispatch.os, "read", read_fault)
    monkeypatch.setattr(dispatch.os, "close", close_and_fail)
    with pytest.raises(OSError) as caught:
        dispatch._manifest_for_dispatch(path)
    assert caught.value is first
    assert caught.value.manifest_cleanup_error is cleanup


def test_discovery_normal_close_failure_cannot_admit_manifest(tmp_path, monkeypatch):
    path = document(tmp_path, profile())
    close = dispatch.os.close

    def close_and_fail(descriptor):
        close(descriptor)
        raise OSError("Descriptor close failed")

    monkeypatch.setattr(dispatch.os, "close", close_and_fail)
    with pytest.raises(OSError, match="Descriptor close failed"):
        dispatch._manifest_for_dispatch(path)


@pytest.mark.parametrize(
    "first_type,cleanup_type",
    [
        (OSError, KeyboardInterrupt),
        (OSError, SystemExit),
        (KeyboardInterrupt, OSError),
        (KeyboardInterrupt, KeyboardInterrupt),
        (KeyboardInterrupt, SystemExit),
        (SystemExit, OSError),
        (SystemExit, KeyboardInterrupt),
        (SystemExit, SystemExit),
    ],
)
def test_discovery_cleanup_interruptions_preserve_exact_first_exception(
    tmp_path, monkeypatch, first_type, cleanup_type
):
    path = document(tmp_path, profile())
    first = first_type("First discovery fault")
    cleanup = cleanup_type("Later descriptor cleanup fault")
    actual_close, closed = dispatch.os.close, []

    def read_fault(*_):
        raise first

    def close_and_fail(descriptor):
        actual_close(descriptor)
        closed.append(descriptor)
        raise cleanup

    monkeypatch.setattr(dispatch.os, "read", read_fault)
    monkeypatch.setattr(dispatch.os, "close", close_and_fail)
    with pytest.raises(BaseException) as caught:
        dispatch._manifest_for_dispatch(path)
    assert caught.value is first
    assert caught.value.manifest_cleanup_error is cleanup
    assert caught.value.manifest_cleanup_errors == (cleanup,)
    assert len(closed) == 1
    with pytest.raises(OSError):
        dispatch.os.fstat(closed[0])


def test_discovery_repeated_first_fault_retains_every_cleanup_exception(
    tmp_path, monkeypatch
):
    path = document(tmp_path, profile())
    first = OSError("Same first discovery fault")
    later = (
        KeyboardInterrupt("First later interruption"),
        OSError("Next cleanup fault"),
        SystemExit("Last later interruption"),
    )
    faults = iter(later)
    actual_close, closed = dispatch.os.close, []

    def read_fault(*_):
        raise first

    def close_and_fail(descriptor):
        actual_close(descriptor)
        closed.append(descriptor)
        raise next(faults)

    monkeypatch.setattr(dispatch.os, "read", read_fault)
    monkeypatch.setattr(dispatch.os, "close", close_and_fail)
    for index, cleanup in enumerate(later):
        with pytest.raises(OSError) as caught:
            dispatch._manifest_for_dispatch(path)
        assert caught.value is first
        assert first.manifest_cleanup_error is cleanup
        assert first.manifest_cleanup_errors == later[: index + 1]
        with pytest.raises(OSError):
            dispatch.os.fstat(closed[-1])
    assert len(closed) == len(later)


@pytest.mark.parametrize("phase", ["read", "close"])
def test_discovery_first_keyboard_interrupt_still_propagates(
    tmp_path, monkeypatch, phase
):
    path = document(tmp_path, profile())
    first = KeyboardInterrupt("First interruption")
    actual_close, closed = dispatch.os.close, []

    def read_fault(*_):
        raise first

    def observed_close(descriptor):
        actual_close(descriptor)
        closed.append(descriptor)
        if phase == "close":
            raise first

    if phase == "read":
        monkeypatch.setattr(dispatch.os, "read", read_fault)
    monkeypatch.setattr(dispatch.os, "close", observed_close)
    with pytest.raises(KeyboardInterrupt) as caught:
        dispatch._manifest_for_dispatch(path)
    assert caught.value is first
    assert not hasattr(first, "manifest_cleanup_errors")
    assert len(closed) == 1
    with pytest.raises(OSError):
        dispatch.os.fstat(closed[0])


def windows_stat_channels(tmp_path, monkeypatch, path, *, legacy_creation=False):
    """Map CPython's two Windows time channels over real local file syscalls.

    This is portable source-unit metadata, not a claim of Windows execution.
    CPython 3.13 path stat copies birthtime into ctime; descriptor stat can expose
    ChangeTime. Older Windows Python lacks birthtime_ns and uses creation ctime.
    All other fields and every open/read/close below come from the actual file.
    """
    from pathlib import Path
    from types import SimpleNamespace

    actual_lstat, actual_fstat = Path.lstat, os.fstat
    births, snapshots = {}, []

    def view(row, channel):
        key = row.st_dev, row.st_ino
        birth = births.setdefault(key, row.st_ctime_ns - 100)
        values = {
            field: getattr(row, field)
            for field in (
                "st_mode",
                "st_dev",
                "st_ino",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        if not legacy_creation:
            values["st_birthtime_ns"] = birth
        if channel == "path" or legacy_creation:
            values["st_ctime_ns"] = birth
        snapshots.append((channel, values.copy()))
        return SimpleNamespace(**values)

    def path_stat(selected, *args, **kwargs):
        row = actual_lstat(selected, *args, **kwargs)
        return view(row, "path") if selected == path else row

    class WindowsOS:
        name = "nt"

        def __getattr__(self, name):
            return getattr(os, name)

        def fstat(self, descriptor):
            return view(actual_fstat(descriptor), "descriptor")

    proxy = WindowsOS()
    monkeypatch.setattr(Path, "lstat", path_stat)
    monkeypatch.setattr(dispatch, "os", proxy)
    return proxy, snapshots


def observed_manifest_io(monkeypatch, proxy):
    opened, chunks, closed = [], [], []
    actual_open, actual_read, actual_close = proxy.open, proxy.read, proxy.close

    def opening(*args, **kwargs):
        descriptor = actual_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def reading(descriptor, size):
        value = actual_read(descriptor, size)
        chunks.append(value)
        return value

    def closing(descriptor):
        actual_close(descriptor)
        closed.append(descriptor)

    monkeypatch.setattr(proxy, "open", opening)
    monkeypatch.setattr(proxy, "read", reading)
    monkeypatch.setattr(proxy, "close", closing)
    return opened, chunks, closed


@pytest.mark.parametrize("legacy_creation", [False, True])
def test_windows_metadata_channels_keep_real_read_and_descriptor_closure(
    tmp_path, monkeypatch, legacy_creation
):
    value = profile()
    value["source_only_unicode_control"] = "e\u0301 🐝"
    path = document(tmp_path, value)
    raw = path.read_bytes()
    proxy, snapshots = windows_stat_channels(
        tmp_path, monkeypatch, path, legacy_creation=legacy_creation
    )
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)
    assert dispatch._manifest_for_dispatch(path) == value
    assert b"".join(chunks) == raw and chunks[-1] == b""
    assert closed == opened and len(closed) == 1
    assert path.read_bytes() == raw
    before, descriptor = snapshots[:2]
    assert before[0] == "path" and descriptor[0] == "descriptor"
    if legacy_creation:
        assert "st_birthtime_ns" not in before[1]
        assert before[1]["st_ctime_ns"] == descriptor[1]["st_ctime_ns"]
    else:
        assert before[1]["st_ctime_ns"] != descriptor[1]["st_ctime_ns"]
        assert before[1]["st_birthtime_ns"] == descriptor[1]["st_birthtime_ns"]
    with pytest.raises(OSError):
        os.fstat(closed[0])


@pytest.mark.parametrize(
    "field", ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_birthtime_ns"]
)
def test_windows_shared_identity_difference_refuses_before_real_read(
    tmp_path, monkeypatch, field
):
    path = document(tmp_path, profile())
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    actual_fstat = proxy.fstat
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)

    def different(descriptor):
        row = actual_fstat(descriptor)
        setattr(row, field, getattr(row, field) + 1)
        return row

    monkeypatch.setattr(proxy, "fstat", different)
    with pytest.raises(ValueError, match="changed before discovery"):
        dispatch._manifest_for_dispatch(path)
    assert chunks == [] and closed == opened and len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])


@pytest.mark.parametrize("channel", ["path", "descriptor"])
@pytest.mark.parametrize(
    "field",
    ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_birthtime_ns"],
)
def test_windows_channel_local_identity_changes_refuse_after_real_read(
    tmp_path, monkeypatch, channel, field
):
    from pathlib import Path

    path = document(tmp_path, profile())
    raw = path.read_bytes()
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    actual_lstat, actual_fstat = Path.lstat, proxy.fstat
    calls = []
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)

    def fstat(descriptor):
        row = actual_fstat(descriptor)
        if channel == "descriptor":
            calls.append(descriptor)
            if len(calls) == 2:
                setattr(row, field, getattr(row, field) + 1)
        return row

    def lstat(selected, *args, **kwargs):
        row = actual_lstat(selected, *args, **kwargs)
        if channel == "path" and selected == path:
            calls.append(selected)
            if len(calls) == 2:
                setattr(row, field, getattr(row, field) + 1)
        return row

    monkeypatch.setattr(proxy, "fstat", fstat)
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(ValueError, match="changed during discovery"):
        dispatch._manifest_for_dispatch(path)
    assert b"".join(chunks) == raw and chunks[-1] == b""
    assert closed == opened and len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_posix_cross_channel_ctime_difference_still_refuses(tmp_path, monkeypatch):
    path = document(tmp_path, profile())
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    # The same explicitly different metadata must never get Windows handling
    # when the syscall interface identifies itself as POSIX.
    proxy.name = "posix"
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)
    with pytest.raises(ValueError, match="changed before discovery"):
        dispatch._manifest_for_dispatch(path)
    assert chunks == [] and closed == opened and len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_windows_actual_same_size_rewrite_cannot_admit_discovery(tmp_path, monkeypatch):
    import time

    path = document(tmp_path, profile())
    raw = path.read_bytes()
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)
    reading = proxy.read
    initial_mtime = path.stat().st_mtime_ns

    def rewrite(descriptor, size):
        value = reading(descriptor, size)
        if len(chunks) == 1:
            time.sleep(0.01)  # Separate actual timestamp ticks, not a new deadline.
            path.write_bytes(raw.replace(b'"latest":false', b'"latest":true '))
            assert path.stat().st_size == len(raw)
            assert path.stat().st_mtime_ns != initial_mtime
        return value

    monkeypatch.setattr(proxy, "read", rewrite)
    with pytest.raises(ValueError, match="changed during discovery"):
        dispatch._manifest_for_dispatch(path)
    assert closed == opened and len(closed) == 1
    assert path.read_bytes() != raw
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_windows_actual_replacement_cannot_bind_old_path_snapshot(
    tmp_path, monkeypatch
):
    path = document(tmp_path, profile())
    raw = path.read_bytes()
    replacement = tmp_path / "new-manifest.json"
    replacement.write_bytes(raw)
    initial = path.stat()
    os.utime(replacement, ns=(initial.st_atime_ns, initial.st_mtime_ns))
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    opened, chunks, closed = observed_manifest_io(monkeypatch, proxy)
    opening = proxy.open

    def replace_then_open(*args, **kwargs):
        os.replace(replacement, path)
        return opening(*args, **kwargs)

    monkeypatch.setattr(proxy, "open", replace_then_open)
    with pytest.raises(ValueError, match="changed before discovery"):
        dispatch._manifest_for_dispatch(path)
    assert chunks == [] and closed == opened and len(closed) == 1
    assert path.read_bytes() == raw
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_windows_metadata_channels_preserve_first_read_and_cleanup_errors(
    tmp_path, monkeypatch
):
    path = document(tmp_path, profile())
    proxy, _snapshots = windows_stat_channels(tmp_path, monkeypatch, path)
    first = OSError("Actual original read refusal after Windows identity binding")
    later = KeyboardInterrupt("Later actual descriptor close interruption")
    actual_close, closed = proxy.close, []

    def read(*_):
        raise first

    def close(descriptor):
        actual_close(descriptor)
        closed.append(descriptor)
        raise later

    monkeypatch.setattr(proxy, "read", read)
    monkeypatch.setattr(proxy, "close", close)
    with pytest.raises(OSError) as caught:
        dispatch._manifest_for_dispatch(path)
    assert caught.value is first
    assert first.manifest_cleanup_error is later
    assert first.manifest_cleanup_errors == (later,)
    assert len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])


def test_native_manifest_stat_channels_record_real_observations(
    tmp_path, monkeypatch, record_testsuite_property
):
    import sys
    from pathlib import Path

    path = document(tmp_path, profile())
    actual_lstat, actual_fstat = Path.lstat, os.fstat
    snapshots = []

    def observe(channel, row):
        snapshots.append(
            {
                "channel": channel,
                **{
                    field: getattr(row, field, None)
                    for field in (
                        "st_mode",
                        "st_dev",
                        "st_ino",
                        "st_size",
                        "st_mtime_ns",
                        "st_ctime_ns",
                        "st_birthtime_ns",
                    )
                },
            }
        )
        return row

    def lstat(selected, *args, **kwargs):
        row = actual_lstat(selected, *args, **kwargs)
        return observe("path", row) if selected == path else row

    def fstat(descriptor):
        return observe("descriptor", actual_fstat(descriptor))

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(dispatch.os, "fstat", fstat)
    try:
        assert dispatch._manifest_for_dispatch(path) == profile()
        assert [row["channel"] for row in snapshots] == [
            "path",
            "descriptor",
            "descriptor",
            "path",
        ]
    finally:
        # Preserve actual host tuples even when a future runtime refuses them;
        # source metadata models cannot establish the values on that host.
        record_testsuite_property(
            "manifest-discovery-native-stat-channels",
            json.dumps(
                {
                    "os_name": os.name,
                    "platform": sys.platform,
                    "python": sys.version,
                    "snapshots": snapshots,
                },
                sort_keys=True,
            ),
        )
