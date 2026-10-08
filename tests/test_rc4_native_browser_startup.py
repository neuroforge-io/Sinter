"""Owned source startup controls; cached mechanics are not installed acceptance."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import rc4_native_handoff as producer
from tools import rc4_native_handoff_contract as contract


LINUX = sys.platform == "linux"


def temporary_record():
    return {
        "path": None,
        "identity_before": None,
        "identity_after": None,
        "removed": False,
    }


@pytest.mark.skipif(not LINUX, reason="Actual Linux temporary-directory mechanics")
def test_exclusive_short_temporary_survives_hostile_ambient_tmpdir(
    tmp_path, monkeypatch
):
    ambient = tmp_path / ("資料🧭" * 18)
    ambient.mkdir()
    monkeypatch.setenv("TMPDIR", str(ambient))
    record = temporary_record()
    producer.create_browser_temporary(record)
    path = Path(record["path"])
    try:
        assert path.parent == Path("/tmp") and len(os.fsencode(path)) <= 55
        assert path.lstat().st_mode == stat.S_IFDIR | 0o700
        assert path.stat().st_uid == os.geteuid()
        assert not path.is_relative_to(ambient)
        (path / "actual-temporary-output").write_bytes(b"owned source fixture")
    finally:
        producer.remove_browser_temporary(record)
    contract.validate_browser_temporary(record)
    assert not os.path.lexists(path) and list(ambient.iterdir()) == []


@pytest.mark.skipif(not LINUX, reason="Actual Linux namespace preflight")
def test_oversize_utf8_namespace_refuses_before_any_allocation(monkeypatch):
    observed = []
    monkeypatch.setattr(contract, "BROWSER_TEMP_PREFIX", "資料🧭" * 18)
    monkeypatch.setattr(
        producer.tempfile, "mkdtemp", lambda **_: observed.append("NOT ALLOWED")
    )
    with pytest.raises(ValueError, match="UTF-8 socket paths"):
        producer.create_browser_temporary(temporary_record())
    assert observed == []


def test_native_run_preflight_stops_before_baseline_or_output(monkeypatch):
    observed = []
    first = ValueError("finite UTF-8 path admission failed")
    monkeypatch.setattr(producer.platform, "system", lambda: "Linux")

    def refuse():
        raise first

    monkeypatch.setattr(contract, "preflight_browser_temporary", refuse)
    monkeypatch.setattr(
        producer.owner, "run", lambda *_: observed.append("NOT ALLOWED")
    )
    with pytest.raises(ValueError) as caught:
        producer.run(SimpleNamespace())
    assert caught.value is first and observed == []


@pytest.mark.skipif(not LINUX, reason="Actual Linux owned-root substitution control")
@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_temporary_cleanup_never_removes_a_replaced_root(tmp_path, replacement):
    record = temporary_record()
    producer.create_browser_temporary(record)
    path = Path(record["path"])
    moved = path.with_name(path.name + "-original")
    target = tmp_path / "must-survive"
    target.mkdir()
    (target / "original").write_bytes(b"outside owned temporary root")
    path.rename(moved)
    if replacement == "directory":
        path.mkdir(mode=0o700)
        (path / "replacement").write_bytes(b"must survive refusal")
    else:
        path.symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="replaced before cleanup"):
            producer.remove_browser_temporary(record)
        assert not record["removed"]
        assert (target / "original").read_bytes() == b"outside owned temporary root"
        if replacement == "directory":
            assert (path / "replacement").read_bytes() == b"must survive refusal"
        else:
            assert path.is_symlink()
    finally:
        if path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path)
        moved.rename(path)
        producer.remove_browser_temporary(record)


@pytest.mark.skipif(not LINUX, reason="Actual Linux safe child-link cleanup")
def test_owned_child_symlink_is_removed_without_following_it(tmp_path):
    record = temporary_record()
    producer.create_browser_temporary(record)
    target = tmp_path / "original.txt"
    target.write_bytes(b"original must survive")
    (Path(record["path"]) / "link").symlink_to(target)
    producer.remove_browser_temporary(record)
    assert target.read_bytes() == b"original must survive"
    contract.validate_browser_temporary(record)


@pytest.mark.skipif(not LINUX, reason="Actual Linux retained-temp refusal")
def test_removed_flag_cannot_admit_a_still_present_owned_root():
    record = temporary_record()
    producer.create_browser_temporary(record)
    record.update(identity_after=dict(record["identity_before"]), removed=True)
    try:
        with pytest.raises(ValueError, match="still exists"):
            contract.validate_browser_temporary(record)
    finally:
        record["removed"] = False
        producer.remove_browser_temporary(record)


def fixture_browser(root, monkeypatch):
    """An inert relay only; this fixture never runs Sinter or a real UI."""
    root.mkdir(parents=True)
    (root.parent.parent / "client").mkdir()
    monkeypatch.setattr(producer, "wait_file", lambda *_: {})
    relay = SimpleNamespace(
        server_address=("127.0.0.1", 32124),
        model_requests=0,
        errors=0,
        serve_forever=lambda: None,
        idle=lambda: True,
        shutdown=lambda: None,
        server_close=lambda: None,
    )
    thread = SimpleNamespace(
        start=lambda: None, join=lambda **_: None, is_alive=lambda: False
    )
    monkeypatch.setattr(producer.transport, "Relay", lambda *_: relay)
    monkeypatch.setattr(producer.threading, "Thread", lambda **_: thread)
    monkeypatch.setattr(producer.native, "binary_digest", lambda *_: "a" * 64)
    monkeypatch.setattr(producer, "port_closed", lambda *_: True)
    return relay


@pytest.mark.skipif(not LINUX, reason="Actual owned child SIGABRT and reap mechanics")
@pytest.mark.parametrize("later_cleanup_failure", [False, True])
def test_early_child_abort_keeps_full_bytes_and_never_starts_playwright(
    tmp_path, monkeypatch, capfd, later_cleanup_failure
):
    root = tmp_path / "handoff-container/out/handoff"
    fixture_browser(root, monkeypatch)
    starts = []
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        SimpleNamespace(
            expect=None, sync_playwright=lambda: starts.append("FORBIDDEN")
        ),
    )
    real_popen = subprocess.Popen
    child_code = (
        "import os,resource,sys;resource.setrlimit(resource.RLIMIT_CORE,(0,0));"
        "sys.stdout.buffer.write(b'owned startup stdout\\n');sys.stdout.flush();"
        "sys.stderr.buffer.write('FIRST startup failure: 資料\\n'.encode());"
        "sys.stderr.flush();os.abort()"
    )
    monkeypatch.setattr(
        producer.subprocess,
        "Popen",
        lambda _argv, **kwargs: real_popen(
            [sys.executable, "-c", child_code], **kwargs
        ),
    )
    real_remove = producer.remove_browser_temporary
    if later_cleanup_failure:

        def denied(_record):
            raise OSError("LATER owned temporary removal failed")

        monkeypatch.setattr(producer, "remove_browser_temporary", denied)
    try:
        with pytest.raises(ValueError, match="exited before its private debugger"):
            producer.browser(root, contract.HOST_CHROMIUM)
        proof = json.loads((root.parent.parent / "browser.json").read_bytes())
        process = proof["chromium_process"]
        assert starts == [] and "driver_process" not in proof
        assert process["exit_code"] == -signal.SIGABRT
        assert process["owned_group_remaining"] is False
        assert process["streams_complete"] is True
        assert (root / "chromium.stdout").read_bytes() == b"owned startup stdout\n"
        assert (root / "chromium.stderr").read_bytes() == (
            "FIRST startup failure: 資料\n".encode()
        )
        assert proof["visible_checks"] == [] and proof["model_requests"] == 0
        if later_cleanup_failure:
            assert proof["cleanup_errors"] == [
                {
                    "role": "browser-temporary.remove",
                    "error_type": "OSError",
                    "error": "LATER owned temporary removal failed",
                }
            ]
            assert proof["temporary_directory"]["removed"] is False
        else:
            contract.validate_browser_temporary(proof["temporary_directory"])
        assert "Task was destroyed" not in capfd.readouterr().err
    finally:
        if "proof" in locals() and not proof["temporary_directory"]["removed"]:
            real_remove(proof["temporary_directory"])


@pytest.mark.skipif(
    not LINUX or not contract.HOST_CHROMIUM.is_file(),
    reason="Uses the existing qualified local Chromium cache only; never downloads",
)
@pytest.mark.parametrize("long_unicode_output", [False, True])
def test_cached_chromium_debugger_and_driver_close_with_owned_short_tmp(
    tmp_path, record_property, long_unicode_output
):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    home = tmp_path / "browser-home"
    if long_unicode_output:
        home = tmp_path / ("資料🧭" * 12) / ("é🧭" * 12) / "browser-home"
    home.mkdir(parents=True)
    assert not long_unicode_output or len(os.fsencode(home)) > 128
    temporary = temporary_record()
    producer.create_browser_temporary(temporary)
    environment = {
        "PATH": os.defpath,
        "HOME": str(home),
        "TMPDIR": temporary["path"],
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    engine = browser = process = None
    row = {}
    streams = {}
    driver_pid = None
    try:
        for name in ("stdout", "stderr"):
            streams[name] = (tmp_path / ("mechanics-chromium." + name)).open("w+b")
        process = subprocess.Popen(
            contract.chromium_argv(home),
            stdin=subprocess.DEVNULL,
            stdout=streams["stdout"],
            stderr=streams["stderr"],
            start_new_session=True,
            env=environment,
        )
        row["pid"] = process.pid
        port = producer.wait_chromium_debugger(process, home)
        before = producer.children()
        engine = producer.start_playwright(sync_playwright, environment)
        drivers = producer.children() - before
        assert len(drivers) == 1 and process.pid not in drivers
        driver_pid = next(iter(drivers))
        browser = engine.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        cdp = browser.new_browser_cdp_session()
        cdp.send("Browser.close")
        assert process.wait(timeout=5) == 0
        browser.close()
        browser = None
        engine.stop()
        engine = None
        assert not producer.alive(driver_pid)
        assert producer.port_closed(port)
    finally:
        if browser is not None:
            browser.close()
        if engine is not None:
            engine.stop()
        if process is not None:
            producer.native.stop_process(process, row)
        for name, stream in streams.items():
            row[name] = producer.menu.stream_record(stream)
            stream.close()
        producer.remove_browser_temporary(temporary)
    assert row["exit_code"] == 0 and row["owned_group_remaining"] is False
    contract.validate_browser_temporary(temporary)
    record_property(
        "native_browser_startup_mechanics",
        json.dumps(
            {
                "installed_acceptance": False,
                "ui_or_model_requests": 0,
                "long_unicode_output": long_unicode_output,
                "temporary": temporary,
                "chromium": row,
                "driver_pid": driver_pid,
                "driver_gone": not producer.alive(driver_pid),
                "debug_port_closed": producer.port_closed(port),
            }
        ),
    )


@pytest.mark.skipif(
    not LINUX or not contract.HOST_CHROMIUM.is_file(),
    reason="Uses the existing local Chromium cache only; never downloads",
)
def test_real_driver_connect_refusal_keeps_primary_and_closes_owned_startup(
    tmp_path, monkeypatch, capfd, record_property
):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import Error

    root = tmp_path / "handoff-container/out/handoff"
    root.mkdir(parents=True)
    (root.parent.parent / "client").mkdir()
    monkeypatch.setattr(producer, "wait_file", lambda *_: {})
    real_start = producer.start_playwright
    selected = []

    def start(factory, environment):
        engine = real_start(factory, environment)
        connect = engine.chromium.connect_over_cdp

        def refused(_actual_debugger):
            try:
                # A closed loopback endpoint, never a model or application route.
                return connect("http://127.0.0.1:1", timeout=2000)
            except Error as error:
                selected.append(error)
                raise

        engine.chromium.connect_over_cdp = refused
        return engine

    monkeypatch.setattr(producer, "start_playwright", start)
    with pytest.raises(Error) as caught:
        producer.browser(root, contract.HOST_CHROMIUM)
    proof = json.loads((root.parent.parent / "browser.json").read_bytes())
    assert caught.value is selected[0] and proof["error"] == str(selected[0])
    assert "ECONNREFUSED" in proof["error"]
    assert proof["visible_checks"] == [] and proof["model_requests"] == 0
    assert proof["cleanup"]["owned_driver_gone"] is True
    assert proof["chromium_process"]["owned_group_remaining"] is False
    assert proof["chromium_process"]["streams_complete"] is True
    assert proof["cleanup"]["relay_stopped"] is True
    assert proof["cleanup"]["relay_port_closed"] is True
    assert proof["cleanup"]["debug_port_closed"] is True
    contract.validate_browser_temporary(proof["temporary_directory"])
    diagnostics = capfd.readouterr().err
    assert "Task was destroyed" not in diagnostics
    assert "Future exception was never retrieved" not in diagnostics
    record_property("actual_connect_refusal_proof", json.dumps(proof))
