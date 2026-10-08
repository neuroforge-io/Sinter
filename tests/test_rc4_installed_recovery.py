"""Finite source/IPC/ownership controls only; no installer or installed pass fixture."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import socket
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tools import rc4_installed_recovery as producer
from tools import rc4_installed_recovery_contract as contract


def synthetic_command_row(argv, stdout=b"", stderr=b""):
    """Typed source-unit metadata only; no actual child or installed admission."""
    from tools.installed_native_menu import stream_record

    return {
        "argv": list(map(str, argv)),
        "pid": 4321,
        "exit_code": 0,
        "owned_group_remaining": False,
        "forced_cleanup": False,
        "streams_complete": True,
        "passed": True,
        "stdout": stream_record(io.BytesIO(stdout)),
        "stderr": stream_record(io.BytesIO(stderr)),
    }


def removal_observation():
    """Synthetic complete rows exercise portable parser predicates only."""
    row = synthetic_command_row(["dpkg", "-r", "sinter"])
    return row, {"package_state": "absent", "remaining_paths": [], "passed": True}


@pytest.fixture
def short_relay_root():
    """Own a short socket root independently of the long pytest basetemp."""
    with tempfile.TemporaryDirectory(prefix="s4-", dir=Path.home()) as directory:
        yield Path(directory)


POSIX_CHILD = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "killpg"),
    reason="Actual process-group child control requires POSIX os.killpg.",
)
UNIX_RELAY = pytest.mark.skipif(
    os.name != "posix"
    or not hasattr(socket, "AF_UNIX")
    or not hasattr(socketserver, "ThreadingUnixStreamServer"),
    reason="Actual Unix relay control requires POSIX Unix stream socketserver.",
)


@pytest.mark.parametrize(
    "change",
    ["missing", "null", "wrong_hash", "unknown_stream_field", "wrong_truncation"],
)
def test_removal_requires_complete_actual_stdout(change):
    row, state = removal_observation()
    contract.validate_package_removal(0, row, state, [row])
    changed = copy.deepcopy(row)
    if change == "missing":
        changed.pop("stdout")
    elif change == "null":
        changed["stdout"] = None
    elif change == "wrong_hash":
        changed["stdout"]["sha256"] = "0" * 64
    elif change == "unknown_stream_field":
        changed["stdout"]["unobserved"] = True
    else:
        changed["stdout"]["truncated"] = True
    # The unique raw command also matches, so stdout admission must refuse it.
    with pytest.raises((KeyError, ValueError)):
        contract.validate_package_removal(0, changed, state, [changed])


def test_removal_preserves_nonempty_progress_and_exact_known_warning():
    from tools import installed_native_entry_contract as native

    progress = b"Removing sinter (synthetic source-unit stream) ...\n"
    row = synthetic_command_row(
        ["dpkg", "-r", "sinter"], progress, contract.REMOVAL_NOTICE
    )
    rows = [row]
    state = {"package_state": "absent", "remaining_paths": [], "passed": True}
    before = copy.deepcopy(row)
    contract.validate_package_removal(0, row, state, rows)
    assert row == before
    assert native.stream_bytes(row["stdout"]) == progress
    assert native.stream_bytes(row["stderr"]) == contract.REMOVAL_NOTICE


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", False),
        ("pid", 1.0),
        ("pid", -1),
        ("pid", None),
        ("forced_cleanup", 0),
        ("owned_group_remaining", None),
        ("owned_group_remaining", 0),
        ("cleanup_error_type", "InertCleanupFault"),
    ],
)
def test_removal_requires_shared_strict_process_ownership(field, value):
    row, state = removal_observation()
    contract.validate_package_removal(0, row, state, [row])
    changed = copy.deepcopy(row)
    if value is None:
        changed.pop(field)
    else:
        changed[field] = value
    with pytest.raises(ValueError):
        contract.validate_package_removal(0, changed, state, [changed])


@pytest.mark.parametrize(
    "change", ["missing", "different", "duplicate", "wrong_argv", "nonobject", "bound"]
)
def test_removal_is_bound_to_its_unique_actual_command(change):
    row, state = removal_observation()
    commands = [copy.deepcopy(row)]
    if change == "missing":
        commands.clear()
    elif change == "different":
        commands[0]["pid"] += 1
    elif change == "duplicate":
        commands.append(copy.deepcopy(row))
    elif change == "wrong_argv":
        commands[0]["argv"] = ["dpkg-query", "sinter"]
    elif change == "nonobject":
        commands.append(None)
    else:
        commands += [{"argv": ["ordinary-fixture"]}] * 256
    with pytest.raises(ValueError, match="command"):
        contract.validate_package_removal(0, row, state, commands)


@pytest.mark.parametrize("initial_cache", [False, True])
def test_host_entrypoint_defers_cache_cleanup_until_outer_reap(
    tmp_path, monkeypatch, initial_cache
):
    for name in ("source", "candidate", "out", "t"):
        (tmp_path / name).mkdir()
    qa = {"sentinel": {"bytes": 1, "sha256": "a" * 64}}
    browser = {"path": "/inert/chrome", "sha256": "b" * 64}
    producer.write_json(
        tmp_path / "candidate/recovery-input.json", {"qa_files": qa, "browser": browser}
    )
    cache = tmp_path / "t/com.google.Chrome.chrome_chrome_url_fetcher_.ABC123"
    called = []

    def profile_body(*args):
        called.append(True)
        cache.mkdir()
        (cache / producer.CACHE_NAME).write_bytes(b"retained inert cache")
        return {"campaign": "inert", "scoped": "inert"}

    if initial_cache:
        cache.mkdir()
        (cache / producer.CACHE_NAME).write_bytes(b"must remain untouched")
    monkeypatch.setattr(producer, "ROOT", tmp_path / "source")
    monkeypatch.setattr(producer, "source_records", lambda root: qa)
    monkeypatch.setattr(producer, "browser_identity", lambda path: browser)
    monkeypatch.setattr(producer, "host_profiles", profile_body)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "t"))
    argv = ["host", "--proof-root", str(tmp_path), "--chromium", "/inert/chrome"]
    if initial_cache:
        with pytest.raises(SystemExit) as refusal:
            producer.main(argv)
        assert refusal.value.code == 1 and called == []
        assert (cache / producer.CACHE_NAME).read_bytes() == b"must remain untouched"
    else:
        assert producer.main(argv) == 0 and called == [True]
        assert (cache / producer.CACHE_NAME).read_bytes() == b"retained inert cache"
        assert producer.read_json(tmp_path / "out/host-resources.json") == {
            "campaign": "inert",
            "scoped": "inert",
        }
        assert not (tmp_path / "out/browser-cache-cleanup.json").exists()


@pytest.mark.parametrize("nested", [False, True])
def test_profile_inventory_cannot_omit_an_unknown_empty_directory(tmp_path, nested):
    (tmp_path / "retained.json").write_bytes(b"{}")
    directory = tmp_path / "unexpected"
    directory.mkdir()
    if nested:
        (directory / "deeper").mkdir()
    with pytest.raises(ValueError, match="empty profile"):
        contract.profile_artifacts(tmp_path)


@pytest.mark.parametrize("profile", ["campaign", "scoped"])
def test_producer_profile_directories_match_used_contract_roles(tmp_path, profile):
    producer.prepare_profile_evidence(tmp_path, profile)
    required = {
        Path(name).parts[0]
        for name in contract.profile_roles(profile)
        if len(Path(name).parts) > 1
    }
    # Ordinary source-unit records exercise the real closed inventory reader,
    # without claiming profile semantics, installed execution or a release pass.
    expected = {}
    for name in sorted(required):
        relative = name + "/source-unit.json"
        raw = contract.canonical({"profile": profile, "role": name}).encode("utf-8")
        (tmp_path / relative).write_bytes(raw)
        expected[relative] = raw
    assert contract.profile_artifacts(tmp_path) == expected
    assert {path.name for path in tmp_path.iterdir()} == required
    if os.name == "posix":
        assert all(
            (tmp_path / name).stat().st_mode & 0o777 == 0o777 for name in required
        )
    (tmp_path / "unexpected").mkdir()
    with pytest.raises(ValueError, match="Unlisted empty profile directories"):
        contract.profile_artifacts(tmp_path)


@pytest.mark.parametrize("profile", ["unknown", None, True])
def test_producer_unknown_profile_refuses_before_creating_evidence(tmp_path, profile):
    with pytest.raises(ValueError, match="Unknown recovery profile"):
        producer.prepare_profile_evidence(tmp_path, profile)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bound", ["entries", "depth"])
def test_profile_inventory_bounds_directories_and_files(tmp_path, monkeypatch, bound):
    if bound == "entries":
        monkeypatch.setattr(contract, "MAX_PROFILE_ENTRIES", 2)
        for index in range(3):
            (tmp_path / (str(index) + ".json")).write_bytes(b"{}")
    else:
        monkeypatch.setattr(contract, "MAX_PROFILE_DEPTH", 2)
        directory = tmp_path / "first/second"
        directory.mkdir(parents=True)
        (directory / "retained.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="finite bound"):
        contract.profile_artifacts(tmp_path)


def request(profile="campaign", operation="snapshot", sequence=1):
    return {
        "schema": contract.RPC_REQUEST,
        "profile": profile,
        "session": "a" * 32,
        "sequence": sequence,
        "operation": operation,
    }


def exchange(tmp_path, profile="campaign"):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "rpc").mkdir()
    (runtime / "data").mkdir()
    output = tmp_path / "proof"
    output.mkdir()
    for n in ("rpc", "inner-rpc", "process"):
        (output / n).mkdir()
    return runtime, output


@pytest.mark.parametrize(
    "profile,operation",
    [("campaign", "snapshot"), ("scoped", "snapshot"), ("scoped", "protocol")],
)
def test_actual_owned_ipc_binds_complete_two_sided_bytes(tmp_path, profile, operation):
    runtime, output = exchange(tmp_path, profile)
    value = {"typed": {"integer": 1, "real": 1.0, "bool": False, "text": "café é 🐝"}}
    paths = []
    server = producer.ObservationServer(
        runtime,
        profile,
        "a" * 32,
        output,
        lambda path: (paths.append(path), value)[1],
        lambda: value,
    )
    client = producer.ObservationClient(runtime, profile, "a" * 32, output, timeout=2)
    result, errors = [], []

    def call():
        try:
            result.append(client.call(operation))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=call)
    thread.start()
    deadline = time.monotonic() + 2
    while not (runtime / "rpc/request.json").exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    server.service()
    thread.join(timeout=2)
    assert not thread.is_alive() and not errors and result == [value]
    for kind in ("request", "response"):
        assert (output / f"rpc/01.{kind}.json").read_bytes() == (
            output / f"inner-rpc/01.{kind}.json"
        ).read_bytes()
    assert paths == ([runtime / "data"] if operation == "snapshot" else [])


@pytest.mark.parametrize(
    "change",
    [
        {"sequence": True},
        {"sequence": 1.0},
        {"sequence": 0},
        {"sequence": 2},
        {"profile": "other"},
        {"session": "b" * 32},
        {"operation": "SELECT * FROM reports"},
        {"path": "/home/other"},
        {"sql": "DROP TABLE reports"},
        {"schema": "sinter-source-worker/v1"},
    ],
)
def test_unknown_or_replayed_ipc_refuses_before_workspace_read(tmp_path, change):
    runtime, output = exchange(tmp_path)
    called = []
    server = producer.ObservationServer(
        runtime,
        "campaign",
        "a" * 32,
        output,
        lambda path: called.append(path),
        lambda: called.append("protocol"),
    )
    bad = {**request(), **change}
    producer.write_json(runtime / "rpc/request.json", bad)
    with pytest.raises(ValueError):
        server.service()
    assert called == [] and (runtime / "rpc/request.json").exists()
    assert json.loads((output / "inner-rpc/01.request.json").read_text()) == bad


def test_callback_maps_only_fixed_current_workspace(tmp_path):
    runtime, output = exchange(tmp_path)
    client = producer.ObservationClient(
        runtime, "campaign", "a" * 32, output, timeout=0.05
    )
    with pytest.raises(ValueError, match="fixed current"):
        client.snapshot(tmp_path / "other/data")
    assert not (runtime / "rpc/request.json").exists()
    with pytest.raises(ValueError, match="Unknown"):
        client.call("protocol")
    assert client.sequence == 0


def test_timeout_keeps_complete_request_without_success(tmp_path):
    runtime, output = exchange(tmp_path)
    client = producer.ObservationClient(
        runtime, "campaign", "a" * 32, output, timeout=0.02
    )
    with pytest.raises(ValueError, match="timed out"):
        client.call("snapshot")
    assert (runtime / "rpc/request.json").read_bytes() == (
        output / "rpc/01.request.json"
    ).read_bytes()
    assert not (output / "rpc/01.response.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"schema": contract.RPC_REQUEST},
        {"session": "b" * 32},
        {"sequence": True},
        {"sequence": 1.0},
        {"profile": "scoped"},
        {"extra": False},
        {"result": []},
        {"error": False},
        {"error": "refused"},
    ],
)
def test_changed_response_identity_or_false_success_refuses(change):
    original = request()
    response = {
        **original,
        "schema": contract.RPC_RESPONSE,
        "result": {},
        "error": None,
    }
    with pytest.raises(ValueError):
        contract.validate_rpc(original, {**response, **change})


def test_observer_error_is_explicit_and_full_input_preserved(tmp_path):
    runtime, output = exchange(tmp_path)

    def refused(path):
        raise ValueError("Fixture changed before reader admission")

    server = producer.ObservationServer(
        runtime, "campaign", "a" * 32, output, refused, refused
    )
    producer.write_json(runtime / "rpc/request.json", request())
    server.service()
    result = json.loads((runtime / "rpc/response.json").read_text())
    contract.validate_rpc(request(), result)
    assert result["result"] is None and "before reader" in result["error"]
    assert (output / "inner-rpc/01.response.json").read_bytes() == (
        runtime / "rpc/response.json"
    ).read_bytes()


def test_observation_cap_is_finite(tmp_path):
    runtime, output = exchange(tmp_path)
    client = producer.ObservationClient(runtime, "campaign", "a" * 32, output)
    client.sequence = 64
    with pytest.raises(ValueError, match="count exceeds"):
        client.call("snapshot")
    assert not (runtime / "rpc/request.json").exists()


def git_tar(commit, files):
    out = io.BytesIO()
    with tarfile.open(
        fileobj=out,
        mode="w",
        format=tarfile.PAX_FORMAT,
        pax_headers={"comment": commit},
    ) as archive:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    return out.getvalue()


def fixture_source(version="0.5.4rc4.dev0"):
    return {
        "src/sinter/__init__.py": f'__version__ = "{version}"\n'.encode(),
        "src/sinter/web/app.js": b"fictional production asset",
        "tools/fixed.py": b"fictional candidate QA",
    }


def test_dev_separate_qa_identity_never_final_candidate_admission():
    files = fixture_source()
    qa = {n: contract.record(v) for n, v in files.items()}
    qa["tools/new-reviewed.py"] = contract.record(b"new separate QA")
    result = producer.source_binding(
        git_tar("a" * 40, files), "a" * 40, qa, "development"
    )
    assert result["qa_files"] != result["files"] and result["mode"] == "development"
    with pytest.raises(ValueError, match="Final RC4"):
        producer.source_binding(git_tar("a" * 40, files), "a" * 40, qa, "candidate")


def test_final_candidate_requires_complete_equal_qa_and_package_source():
    files = fixture_source("0.5.4rc4")
    qa = {n: contract.record(v) for n, v in files.items()}
    result = producer.source_binding(
        git_tar("a" * 40, files), "a" * 40, qa, "candidate"
    )
    assert result["files"] == result["qa_files"]
    with pytest.raises(ValueError):
        producer.source_binding(
            git_tar("a" * 40, files),
            "a" * 40,
            {**qa, "tools/extra.py": contract.record(b"bad")},
            "candidate",
        )


@pytest.mark.parametrize(
    "case",
    [
        "production-changed",
        "production-extra",
        "different-origin",
        "old-version",
        "unknown-mode",
    ],
)
def test_source_production_and_exact_boundary_refusals(case):
    files = fixture_source()
    qa = {n: contract.record(v) for n, v in files.items()}
    commit = "a" * 40
    mode = "development"
    if case == "production-changed":
        qa["src/sinter/web/app.js"] = contract.record(b"different")
    if case == "production-extra":
        qa["src/sinter/extra.py"] = contract.record(b"extra")
    if case == "different-origin":
        commit = "b" * 40
    if case == "old-version":
        files = fixture_source("0.5.4rc3")
        qa = {n: contract.record(v) for n, v in files.items()}
    if case == "unknown-mode":
        mode = "source"
    with pytest.raises(ValueError):
        producer.source_binding(git_tar("a" * 40, files), commit, qa, mode)


def test_fixed_installed_argv_does_not_use_source_worker(tmp_path):
    assert producer.process_argv(tmp_path / "data") == [
        "/opt/neuroforge/sinter/Sinter",
        "app",
        "--mode",
        "browser",
        "--directory",
        str(tmp_path / "data"),
    ]
    env = producer.environment(tmp_path / "home", tmp_path / "capture-browser")
    assert set(env) == {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "BROWSER",
        "PYTHONDONTWRITEBYTECODE",
    }
    assert "DISPLAY" not in env and "XAUTHORITY" not in env and "PYTHONPATH" not in env


def test_container_creation_keeps_reviewed_isolation_and_fixed_mounts(tmp_path):
    from tools.installed_native_container import pins_for

    pins = pins_for(tmp_path, "a" * 64, "b" * 40, "fictional.deb", "fictional.json")
    argv = producer.outer_argv(pins, "sinter-native-entry-123456abcdef")
    assert argv[-4:] == [
        "python3",
        "-B",
        "/source/tools/rc4_installed_recovery.py",
        "inner",
    ]
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert argv[argv.index("--user") + 1] == "0:0"
    assert argv.count("--mount") == 4 and "--privileged" not in argv
    assert "--pull=never" in argv and producer.IMAGE in argv


def test_symlinked_request_is_refused_without_reader(tmp_path):
    runtime, output = exchange(tmp_path)
    outside = tmp_path / "outside.json"
    producer.write_json(outside, request())
    (runtime / "rpc/request.json").symlink_to(outside)
    server = producer.ObservationServer(
        runtime,
        "campaign",
        "a" * 32,
        output,
        lambda path: pytest.fail("reader ran"),
        lambda: pytest.fail("protocol ran"),
    )
    with pytest.raises(ValueError):
        server.service()
    assert json.loads(outside.read_text()) == request()


def test_complete_binary_bytes_and_nonfinite_json_refuse(tmp_path):
    assert (
        contract.full(contract.record_full(b"\x00\xff callback\n"))
        == b"\x00\xff callback\n"
    )
    with pytest.raises(ValueError):
        contract.full({**contract.record_full(b"x"), "bytes": True})
    with pytest.raises(ValueError):
        contract.json_object(b'{"x":NaN}')
    with pytest.raises(ValueError):
        contract.json_object(b'{"x":1,"x":2}')


def test_raw_conservation_guard_precedes_any_reader_and_does_not_repair(tmp_path):
    sys.path.insert(0, str(producer.ROOT / "src"))
    import sqlite3

    from tools.rc4_recovery_worker import seed, snapshot

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output = tmp_path / "proof"
    output.mkdir()
    (output / "process").mkdir()
    baseline = seed(runtime / "data")["snapshot"]
    with sqlite3.connect(runtime / "data/workspace.sqlite3") as db:
        db.execute("PRAGMA user_version=0")
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.profile, lifecycle.baseline = (
        runtime,
        output,
        "campaign",
        baseline,
    )
    before = snapshot(runtime / "data")
    with pytest.raises(ValueError, match="before installed reader"):
        lifecycle.admission("run-1")
    assert contract.equal(snapshot(runtime / "data"), before)
    assert (
        json.loads(
            (output / "process/run-1.before-reader.json").read_text(encoding="utf-8")
        )
        == before
    )
    assert before["databases"]["workspace.sqlite3"]["metadata"]["user_version"] == 0


def test_real_finite_process_diagnostics_survive_later_snapshot_failure(
    tmp_path, monkeypatch
):

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    output = tmp_path / "proof"
    output.mkdir()
    (output / "process").mkdir()
    paths = {name: output / f"process/run-1.{name}" for name in ("stdout", "stderr")}
    streams = [paths[n].open("wb") for n in ("stdout", "stderr")]
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import os;os.write(2,b'\\xff callback failure\\n')",
        ],
        stdin=subprocess.DEVNULL,
        stdout=streams[0],
        stderr=streams[1],
        start_new_session=True,
    )
    process.wait(timeout=2)
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.process = runtime, output, process
    lifecycle.paths, lifecycle.streams, lifecycle.notice = (
        paths,
        streams,
        b"normal notice",
    )
    lifecycle.inner = SimpleNamespace(port=1)
    lifecycle.rows = [{"run": 1, "pid": process.pid}]
    monkeypatch.setattr(
        producer,
        "fixed_snapshot",
        lambda p: (_ for _ in ()).throw(ValueError("observation failed")),
    )
    with pytest.raises(ValueError, match="observation failed"):
        lifecycle.reap(1)
    row = json.loads((output / "process/run-1.json").read_text())
    assert row["stderr"]["bytes"] == len(b"\xff callback failure\n")
    assert (
        row["stderr"]["sha256"]
        == hashlib.sha256(b"\xff callback failure\n").hexdigest()
    )
    assert row["stderr"]["sample_complete"] is True and process.poll() == 0


def test_closed_role_sets_require_both_profiles_and_no_old_worker_controls():
    for profile in ("campaign", "scoped"):
        roles = contract.profile_roles(profile)
        assert "seed-control.json" not in roles and "seed.json" in roles
        assert "host-observations.json" in roles and "processes.json" in roles
        assert "rpc/01.request.json" in roles and "inner-rpc/01.request.json" in roles
        assert "process/run-1.before-reader.json" in roles
    assert "process/run-6.json" in contract.profile_roles("campaign")
    assert "process/run-4.cli-export.json" in contract.profile_roles("scoped")


@pytest.mark.parametrize(
    "field,value",
    [
        ("stale_posts", False),
        ("stale_posts", 0.0),
        ("initial_revision", True),
        ("initial_revision", 1.0),
    ],
)
def test_installed_ui_semantics_preserve_exact_source_type_refusals(
    tmp_path, monkeypatch, field, value
):
    from test_rc4_scoped_recovery import ProtocolBoundary, semantic_data_before_protocol

    from tools.rc4_recovery_worker import seed

    initial = seed(tmp_path / "data")
    raw, observe = semantic_data_before_protocol(initial)
    raw["seed.json"] = raw.pop("seed-control.json")
    sentinel = b"finite-unit-protocol-boundary"
    raw["protocol.json"] = sentinel
    original = contract.json_object

    def read(value):
        if value is sentinel:
            raise ProtocolBoundary
        return original(value)

    monkeypatch.setattr(contract, "json_object", read)
    raw["observations.json"] = contract.canonical(observe).encode()
    with pytest.raises(ProtocolBoundary):
        contract.validate_scoped(raw)
    if field == "stale_posts":
        observe["stale_scope"]["posts"] = value
    else:
        observe["conflict"]["initial"]["revision"] = value
    raw["observations.json"] = contract.canonical(observe).encode()
    with pytest.raises(ValueError):
        contract.validate_scoped(raw)


@pytest.mark.parametrize("branch", ["clipboard", "manual"])
@pytest.mark.parametrize("change", ["bool_start", "float_start", "float_end"])
def test_installed_ui_complete_backup_selection_keeps_builtin_integer_bounds(
    tmp_path, monkeypatch, branch, change
):
    from test_rc4_scoped_recovery import ProtocolBoundary, semantic_data_before_protocol

    from tools.rc4_recovery_worker import seed

    initial = seed(tmp_path / "data")
    raw, observe = semantic_data_before_protocol(initial)
    raw["seed.json"] = raw.pop("seed-control.json")
    sentinel = b"finite-unit-protocol-boundary"
    raw["protocol.json"] = sentinel
    original = contract.json_object

    def read(value):
        if value is sentinel:
            raise ProtocolBoundary
        return original(value)

    monkeypatch.setattr(contract, "json_object", read)
    raw["observations.json"] = contract.canonical(observe).encode()
    with pytest.raises(ProtocolBoundary):
        contract.validate_scoped(raw)
    values = observe["offline"][branch]["selection"]
    if change == "float_end":
        values[1] = float(values[1])
    else:
        values[0] = False if change == "bool_start" else 0.0
    raw["observations.json"] = contract.canonical(observe).encode()
    with pytest.raises(ValueError):
        contract.validate_scoped(raw)


@pytest.mark.parametrize(
    "schema",
    [
        "sinter-rc4-scoped-casebook-source/v1",
        "sinter-rc4-local-recovery-source/v1",
        "sinter-installed-recovery/v1",
    ],
)
def test_source_and_historical_receipt_never_new_installed_admission(tmp_path, schema):
    with pytest.raises(ValueError, match="distinct complete installed"):
        contract.validate(
            tmp_path, {"schema": schema, "frozen": False, "passed": True}, {}, {}
        )


def scoped_lifecycle(tmp_path):
    from test_rc4_scoped_recovery import scoped_fixture

    from sinter.casebooks import Casebooks
    from sinter.store import Store
    from tools.rc4_recovery_worker import seed, snapshot

    runtime, output = exchange(tmp_path, "scoped")
    (runtime / "data").rmdir()
    initial = seed(runtime / "data")
    Casebooks(Store(runtime / "data")).save(scoped_fixture())
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.profile = runtime, output, "scoped"
    lifecycle.baseline, lifecycle.identity = (
        initial["snapshot"],
        {"version": "fictional-version"},
    )
    return lifecycle, snapshot(runtime / "data")


def test_cli_cleanup_fault_retains_actual_nonutf8_diagnostics_and_first_admission(
    tmp_path, monkeypatch
):
    from tools import installed_native_menu as menu

    lifecycle, before = scoped_lifecycle(tmp_path)
    called = []

    def failed(argv, rows, **kw):
        called.append(list(map(str, argv)))
        raw = b"\xff owned CLI diagnostic\n"
        rows.append(synthetic_command_row(argv, stderr=raw))
        for name, path in kw["save_streams"].items():
            path.write_bytes(raw if name == "stderr" else b"")
        rows[-1]["cleanup_error_type"] = "RuntimeError"
        raise RuntimeError("owned cleanup observation failed")

    monkeypatch.setattr(menu, "command", failed)
    with pytest.raises(RuntimeError, match="owned cleanup"):
        lifecycle.cli_readers(1, before)
    row = producer.read_json(lifecycle.output / "process/run-1.cli.json")
    assert len(called) == 1 and set(row["operations"]) == {"casebooks.get"}
    observed = row["operations"]["casebooks.get"]
    raw = (lifecycle.output / "process/run-1.casebooks-get.stderr").read_bytes()
    assert raw == b"\xff owned CLI diagnostic\n"
    assert observed["stderr"]["bytes"] == len(raw)
    assert observed["stderr"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert observed["streams_complete"] is True and row["after"] is None
    assert contract.equal(row["reader_snapshots"]["casebooks.get"]["before"], before)
    assert (
        lifecycle.output / "process/run-1.casebooks-get.before-reader.json"
    ).exists()


def test_cli_record_change_refuses_before_any_next_reader(tmp_path, monkeypatch):
    import sqlite3

    from tools import installed_native_menu as menu
    from tools.rc4_recovery_worker import snapshot

    lifecycle, before = scoped_lifecycle(tmp_path)
    called = []

    def changed(argv, rows, **kw):
        called.append(list(map(str, argv)))
        raw = (
            b'{"schema":"sinter-operation-result/v1","operation":"casebooks.get",'
            b'"ok":true,"version":"fictional-version"}\n'
        )
        rows.append(synthetic_command_row(argv, stdout=raw))
        for name, path in kw["save_streams"].items():
            path.write_bytes(raw if name == "stdout" else b"")
        with sqlite3.connect(lifecycle.runtime / "data/workspace.sqlite3") as db:
            db.execute("PRAGMA application_id=987")
        return 0, raw

    monkeypatch.setattr(menu, "command", changed)
    with pytest.raises(ValueError, match="changed typed"):
        lifecycle.cli_readers(1, before)
    row = producer.read_json(lifecycle.output / "process/run-1.cli.json")
    assert len(called) == 1 and set(row["operations"]) == {"casebooks.get"}
    after = snapshot(lifecycle.runtime / "data")
    assert after["databases"]["workspace.sqlite3"]["metadata"]["application_id"] == 987
    assert contract.equal(row["reader_snapshots"]["casebooks.get"]["after"], after)
    assert contract.equal(
        producer.read_json(
            lifecycle.output / "process/run-1.casebooks-get.after-reader.json"
        ),
        after,
    )


@pytest.mark.parametrize(
    "diagnostic",
    [
        b"",
        contract.REMOVAL_NOTICE,
        b"unexpected callback\n",
        contract.REMOVAL_NOTICE + b"extra\n",
    ],
)
def test_exact_removal_notice_never_hides_other_actual_bytes(tmp_path, diagnostic):
    rows = [synthetic_command_row(["dpkg", "-r", "sinter"], stderr=diagnostic)]
    state = {"package_state": "absent", "remaining_paths": [], "passed": True}
    if diagnostic in (b"", contract.REMOVAL_NOTICE):
        contract.validate_package_removal(0, rows[-1], state, rows)
    else:
        with pytest.raises(ValueError, match="Unexpected package"):
            contract.validate_package_removal(0, rows[-1], state, rows)


@POSIX_CHILD
@pytest.mark.parametrize(
    "stdout,stderr",
    [
        (b"", b""),
        (b"ordinary child progress\n", contract.REMOVAL_NOTICE),
        (b"", b"\xff owned CLI diagnostic\n"),
    ],
)
def test_actual_posix_child_keeps_complete_streams_and_process_ownership(
    stdout, stderr
):
    """Real finite child; neither dpkg nor an installed application is executed."""
    from tools import installed_native_entry_contract as native
    from tools import installed_native_menu as menu

    rows = []
    code, raw = menu.command(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import os;os.write(1,"
            + repr(stdout)
            + ");os.write(2,"
            + repr(stderr)
            + ")",
        ],
        rows,
    )
    native.stopped(rows[-1])
    assert code == 0 and raw == stdout and rows[-1]["streams_complete"] is True
    assert native.stream_bytes(rows[-1]["stdout"]) == stdout
    assert native.stream_bytes(rows[-1]["stderr"]) == stderr


@pytest.mark.parametrize(
    "raw,exit_code,reaped",
    [
        (b"a" * 64 + b"\n", 0, True),
        (b"a" * 64 + b"\nextra", 0, True),
        (b"a" * 64 + b"\n", False, True),
        (b"a" * 64 + b"\n", 1, True),
        (b"a" * 64 + b"\n", 0, False),
        (b"container-name\n", 0, True),
    ],
)
def test_cleanup_id_admission_requires_full_successful_create(raw, exit_code, reaped):
    from tools.installed_native_menu import stream_record

    stdout, stderr = stream_record(io.BytesIO(raw)), stream_record(io.BytesIO(b""))
    row = {
        "role": "create",
        "exit_code": exit_code,
        "reaped": reaped,
        "stdout": stdout,
        "stderr": stderr,
    }
    if (
        raw == b"a" * 64 + b"\n"
        and type(exit_code) is int
        and exit_code == 0
        and reaped
    ):
        assert contract.admitted_create(row, raw) == "a" * 64
    else:
        with pytest.raises(ValueError, match="no cleanup ID"):
            contract.admitted_create(row, raw)


@UNIX_RELAY
def test_actual_unix_partial_request_worker_is_closed_before_ownership_pass(
    short_relay_root,
):
    tmp_path = short_relay_root

    relay = producer.owned_inner_relay(tmp_path)
    thread = threading.Thread(target=relay.serve_forever, daemon=True)
    thread.start()
    client = socket.socket(socket.AF_UNIX)
    try:
        client.connect(str(tmp_path / "relay.sock"))
        client.sendall(b"GET /api/state HTTP/1.1\r\n")
        deadline = time.monotonic() + 2
        while relay.idle() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not relay.idle()
        relay.shutdown()
        relay.server_close()
        thread.join(timeout=2)
        deadline = time.monotonic() + 2
        while not relay.idle() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert relay.idle() and not thread.is_alive()
    finally:
        client.close()
        if thread.is_alive():
            relay.shutdown()
            relay.server_close()
            thread.join(timeout=2)
        (tmp_path / "relay.sock").unlink(missing_ok=True)


def test_inner_ui_observations_are_bound_to_exact_complete_rpc_results(tmp_path):
    from tools.rc4_recovery_worker import seed

    value = seed(tmp_path / "data")["snapshot"]
    data = {"seed.json": json.dumps({"seed": {"snapshot": value}}).encode()}
    responses = [("snapshot", value)] * 6
    contract.validate_observation_results(data, "campaign", responses)
    changed = json.loads(json.dumps(value))
    changed["preferences"]["model"] = "changed-without-original-rewrite"
    with pytest.raises(ValueError, match="original records"):
        contract.validate_observation_results(
            data, "campaign", responses[:5] + [("snapshot", changed)]
        )
    with pytest.raises(ValueError, match="order"):
        contract.validate_observation_results(
            data, "campaign", [("protocol", value)] + responses[1:]
        )


def test_headless_launch_file_identity_refuses_missing_or_changed_bytes(tmp_path):
    path = tmp_path / "fictional-browser"
    path.write_bytes(b"fictional-launch-file-v1")
    path.chmod(0o700)
    original = producer.browser_identity(str(path))
    assert original["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(b"fictional-launch-file-v2")
    assert original != producer.browser_identity(str(path))
    with pytest.raises(ValueError, match="Select an existing"):
        producer.browser_identity(None)


@pytest.mark.parametrize("operation", ["read", "read-failure", "seed", "seed-failure"])
def test_recovery_sqlite_connections_close_on_success_and_first_failure(
    tmp_path, monkeypatch, operation
):
    import sqlite3

    from tools import rc4_recovery_worker as worker

    initial = worker.seed(tmp_path / "initial")
    connections = []
    actual_connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            try:
                super().close()
            finally:
                self.closed = True

        def execute(self, sql, *args, **kwargs):
            if operation == "read-failure" and sql == "PRAGMA query_only=ON":
                raise RuntimeError("first snapshot read failure")
            if operation == "seed-failure" and sql == "PRAGMA application_id=12341":
                raise RuntimeError("first seed metadata failure")
            return super().execute(sql, *args, **kwargs)

    def connect(*args, **kwargs):
        result = actual_connect(*args, factory=TrackedConnection, **kwargs)
        connections.append(result)
        return result

    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        if operation.endswith("failure"):
            with pytest.raises(RuntimeError, match="first .* failure"):
                if operation.startswith("read"):
                    worker.snapshot(tmp_path / "initial")
                else:
                    worker.seed(tmp_path / "new")
        elif operation == "read":
            assert contract.equal(
                worker.snapshot(tmp_path / "initial"), initial["snapshot"]
            )
        else:
            assert worker.seed(tmp_path / "new")["snapshot"]["databases"]
        assert connections and all(db.closed for db in connections)
    finally:
        # Keep failing old controls owned; cleanup never hides the first assertion.
        for db in connections:
            db.close()


def test_fixed_snapshot_preserves_typed_raw_rows_and_refuses_redirected_database(
    tmp_path,
):
    from tools.rc4_recovery_worker import seed, snapshot

    data = tmp_path / "data"
    seed(data)
    assert contract.equal(producer.fixed_snapshot(data), snapshot(data))
    target = tmp_path / "original-sqlite"
    (data / "workspace.sqlite3").rename(target)
    (data / "workspace.sqlite3").symlink_to(target)
    original = target.read_bytes()
    with pytest.raises(ValueError, match="regular file"):
        producer.fixed_snapshot(data)
    assert target.read_bytes() == original


def test_verify_help_is_readonly_and_requires_external_pins():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(producer.ROOT / "tools/rc4_installed_recovery.py"),
            "verify",
            "--help",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0 and result.stderr == b""
    assert (
        b"--source-commit" in result.stdout and b"--installer-sha256" in result.stdout
    )
    assert (
        b"--package-receipt-sha256" in result.stdout
        and b"--owner-sha256" in result.stdout
    )
    assert b"--skip" not in result.stdout


class InertBodyError(RuntimeError):
    pass


class InertCloseError(RuntimeError):
    pass


@pytest.fixture
def inert_playwright_api(monkeypatch):
    """Inject only the inert API; core source controls need no browser package."""
    api = ModuleType("playwright.sync_api")

    def unconfigured(*args, **kwargs):
        raise AssertionError("Unconfigured inert browser API cannot run browser work")

    api.sync_playwright = unconfigured
    api.expect = unconfigured
    package = ModuleType("playwright")
    package.__path__ = []
    package.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    return api


@pytest.fixture
def inert_browser(monkeypatch, inert_playwright_api):
    api = inert_playwright_api

    from tools import _support

    calls, faults = [], set()

    def close(name):
        calls.append(name)
        if name in faults:
            raise InertCloseError("secondary " + name)

    class Context:
        def close(self):
            close("context")

        def new_page(self):
            class Page:
                def goto(self, *args, **kwargs):
                    raise InertBodyError("primary UI body")

                def __getattr__(self, name):
                    return lambda *args, **kwargs: None

            return Page()

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class Browser:
        def new_context(self, **kwargs):
            return Context()

        def close(self):
            close("browser")

    class Driver:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            close("driver")
            return False

    monkeypatch.setattr(api, "sync_playwright", Driver)
    monkeypatch.setattr(_support, "launch_chromium", lambda *args: Browser())
    return calls, faults


@pytest.mark.parametrize(
    "body,failing",
    [
        (True, ()),
        (False, ("context",)),
        (True, ("context",)),
        (True, ("context", "browser", "driver")),
        (False, ("context", "browser", "driver")),
    ],
)
def test_owned_session_preserves_primary_and_attempts_all_closes(
    inert_browser, body, failing
):
    calls, faults = inert_browser
    faults.update(failing)
    session = producer.OwnedBrowserSession("inert")
    expected = InertBodyError if body else InertCloseError
    with pytest.raises(
        expected, match="primary UI body" if body else "secondary context"
    ):
        with session() as driver:
            browser = session.launch(driver, "inert")
            browser.new_context()
            try:
                if body:
                    raise InertBodyError("primary UI body")
            finally:
                browser.close()
    assert {"context", "browser", "driver"} <= set(calls)
    observation = session.observations()
    assert len(observation["cleanup_attempts"]) >= 4
    assert {row["resource"] for row in observation["cleanup_errors"]} >= set(failing)
    assert observation["driver_closed"] is ("driver" not in failing)
    assert observation["browser_closed"] is ("browser" not in failing)
    assert observation["contexts_closed"] is ("context" not in failing)


@pytest.mark.parametrize("kind", ["legacy", "advanced", "scoped"])
def test_actual_shared_ui_seam_preserves_body_when_all_closes_fail(
    tmp_path, monkeypatch, inert_browser, kind
):
    from tools import installed_recovery_browser as legacy
    from tools import rc4_recovery_source as advanced
    from tools import rc4_scoped_recovery_source as scoped

    calls, faults = inert_browser
    faults.update(("context", "browser", "driver"))
    session = producer.OwnedBrowserSession(kind)
    args = SimpleNamespace(output=tmp_path, chromium="inert", source_fixture=True)
    relay = SimpleNamespace(server_address=("127.0.0.1", 1))
    if kind == "advanced":
        monkeypatch.setattr(advanced.transport, "wait_state", lambda *args: None)

        def call():
            return advanced.advanced_workflow(
                args, tmp_path, relay, {}, browser_session=session
            )
    elif kind == "scoped":

        def call():
            return scoped.browser_workflow(
                args, tmp_path, relay, browser_session=session
            )
    else:
        source = {
            p.relative_to(producer.ROOT).as_posix(): p.read_bytes()
            for p in (producer.ROOT / "src/sinter/web").iterdir()
            if p.is_file()
        }

        def call():
            return legacy.browser_workflow(
                args, tmp_path, relay, source, browser_session=session
            )

    with pytest.raises(InertBodyError, match="primary UI body"):
        call()
    assert {"context", "browser", "driver"} <= set(calls)
    assert {row["resource"] for row in session.errors} >= {
        "context",
        "browser",
        "driver",
    }


@pytest.mark.parametrize("body", [True, False])
def test_host_cleanup_keeps_all_diagnostics_and_failed_response(tmp_path, body):
    calls = []
    runtime, output = exchange(tmp_path)

    def fail(name):
        calls.append(name)
        raise InertCloseError("secondary " + name)

    relay = SimpleNamespace(
        shutdown=lambda: fail("shutdown"),
        server_close=lambda: fail("close"),
        idle=lambda: fail("observation"),
        model_requests=0,
        errors=0,
    )
    thread = SimpleNamespace(join=lambda **kwargs: fail("join"), is_alive=lambda: False)
    primary = InertBodyError("primary UI body") if body else None
    result, error = producer.close_host_profile(
        runtime, output, relay, thread, SimpleNamespace(sequence=1), [], primary
    )
    assert error is primary if body else isinstance(error, InertCloseError)
    assert calls == ["shutdown", "close", "join", "observation"]
    assert len(result["cleanup_errors"]) == 4 and len(result["cleanup_attempts"]) == 4
    assert producer.read_json(output / "host-observations.json") == result
    assert result["body_failure"] == (
        {"type": "InertBodyError", "message": "primary UI body"} if body else None
    )


def test_host_failed_response_write_never_masks_primary(tmp_path, monkeypatch, capsys):
    runtime, output = exchange(tmp_path)
    original = producer.write_json

    def write(path, value):
        if path.name == "host-observations.json":
            raise OSError("inert response retention failure")
        original(path, value)

    monkeypatch.setattr(producer, "write_json", write)
    primary = InertBodyError("primary UI body")
    relay = SimpleNamespace(
        shutdown=lambda: None,
        server_close=lambda: None,
        idle=lambda: True,
        model_requests=0,
        errors=0,
    )
    thread = SimpleNamespace(join=lambda **kwargs: None, is_alive=lambda: False)
    result, error = producer.close_host_profile(
        runtime, output, relay, thread, SimpleNamespace(sequence=0), [], primary
    )
    assert (
        error is primary
        and result["cleanup_errors"][-1]["resource"] == "host response retention"
    )
    assert "retention failure" in capsys.readouterr().err


@pytest.mark.parametrize("result", ["body", "nonfinite", "oversize"])
def test_rpc_refusal_retains_complete_failed_response(tmp_path, result):
    runtime, output = exchange(tmp_path)

    def callback(path):
        if result == "body":
            raise InertBodyError("primary observation")
        return {
            "value": float("nan") if result == "nonfinite" else "x" * producer.MAX_RPC
        }

    server = producer.ObservationServer(
        runtime, "campaign", "a" * 32, output, callback, lambda: None
    )
    producer.write_json(runtime / "rpc/request.json", request())
    server.service()
    actual = producer.read_json(runtime / "rpc/response.json")
    assert actual["result"] is None and type(actual["error"]) is str
    assert (runtime / "rpc/response.json").read_bytes() == (
        output / "inner-rpc/01.response.json"
    ).read_bytes()
    contract.validate_rpc(request(), actual)


def test_atomic_rpc_write_failure_keeps_complete_unpublished_bytes(
    tmp_path, monkeypatch
):
    runtime, output = exchange(tmp_path)
    server = producer.ObservationServer(
        runtime,
        "campaign",
        "a" * 32,
        output,
        lambda path: {"value": "original"},
        lambda: None,
    )
    producer.write_json(runtime / "rpc/request.json", request())
    original = type(runtime).replace

    def replace(path, target):
        if target == runtime / "rpc/response.json":
            raise OSError("inert response publication failed")
        return original(path, target)

    monkeypatch.setattr(type(runtime), "replace", replace)
    with pytest.raises(OSError, match="publication failed"):
        server.service()
    assert not (runtime / "rpc/response.json").exists()
    assert (runtime / "rpc/response.tmp").read_bytes() == (
        output / "inner-rpc/01.response.json"
    ).read_bytes()
    assert producer.read_json(runtime / "rpc/response.tmp")["result"] == {
        "value": "original"
    }


def test_non_png_screenshot_bytes_refuse_before_semantic_admission(tmp_path):
    (tmp_path / "warning.png").write_bytes(
        b"literal warning text cannot stand in for pixels"
    )
    with pytest.raises(ValueError, match="PNG"):
        contract.profile_artifacts(tmp_path)


@pytest.mark.parametrize(
    "field", ["body_failure", "cleanup_errors", "missing_driver", "missing_attempt"]
)
def test_incomplete_or_failed_browser_resources_refuse(field):
    session = {
        "phase": "scoped-base",
        "driver_closed": True,
        "browser_closed": True,
        "contexts_closed": True,
        "cleanup_errors": [],
        "cleanup_attempts": [
            {"resource": r, "succeeded": True}
            for r in ("context", "browser", "browser final", "driver")
        ],
    }
    host = {
        "relay_closed": True,
        "model_route_requests": 0,
        "relay_errors": 0,
        "observation_requests": 15,
        "body_failure": None,
        "cleanup_errors": [],
        "browser_sessions": [session],
        "cleanup_attempts": [
            {"resource": r, "succeeded": True}
            for r in (
                "installed cleanup request",
                "relay shutdown",
                "relay close",
                "relay join",
            )
        ],
    }
    contract.validate_host_observations(host, "scoped")
    if field == "body_failure":
        host[field] = {"type": "BodyError", "message": "failed"}
    elif field == "cleanup_errors":
        host[field] = [{"message": "failed"}]
    elif field == "missing_driver":
        session["driver_closed"] = False
    else:
        session["cleanup_attempts"].pop()
    with pytest.raises(ValueError):
        contract.validate_host_observations(host, "scoped")


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "raw_payload",
        "binary_record",
        "menu_record",
        "control",
        "index_bool",
        "stream_hash",
    ],
)
def test_complete_package_sidecars_bind_payload_binary_menu_and_controls(
    tmp_path, mutation
):
    # Pure inert predicate fixture; no archive is installed or executable loaded.
    from tools import installed_native_menu as menu
    from tools.package_native import debian_package_version, linux_desktop_entries

    evidence = tmp_path / "out/evidence"
    evidence.mkdir(parents=True)
    entries = linux_desktop_entries(True)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, body in [
            ("opt/neuroforge/sinter/Sinter", b"never-loaded fictional binary"),
            *[("usr/share/applications/" + n, v.encode()) for n, v in entries.items()],
        ]:
            item = tarfile.TarInfo(name)
            item.size = len(body)
            tar.addfile(item, io.BytesIO(body))
    payload = raw.getvalue()
    members = menu.package_members(payload)
    rows = []
    version = "0.5.4rc4.dev0"

    def row(argv, stdout):
        return {
            "argv": argv,
            "pid": 123,
            "exit_code": 0,
            "owned_group_remaining": False,
            "streams_complete": True,
            "stdout": menu.stream_record(io.BytesIO(stdout)),
            "stderr": menu.stream_record(io.BytesIO(b"")),
        }

    for field, value in (
        ("Package", "sinter"),
        ("Architecture", "amd64"),
        ("Version", debian_package_version(version)),
    ):
        rows.append(
            row(
                ["dpkg-deb", "-f", "/candidate/fictional.deb", field],
                (value + "\n").encode(),
            )
        )
    extracted = row(["dpkg-deb", "--fsys-tarfile", "/candidate/fictional.deb"], payload)
    for name, body in (("stdout", payload), ("stderr", b"")):
        (evidence / ("package." + name)).write_bytes(body)
        extracted[name + "_file"] = "/out/evidence/package." + name
    rows.append(extracted)
    binary = members["opt/neuroforge/sinter/Sinter"]
    package = {
        "payload_tar_bytes": len(payload),
        "payload_tar_sha256": contract.sha(payload),
        "binary_bytes": len(binary),
        "binary_sha256": contract.sha(binary),
        "entries": {
            n: contract.record_full(members["usr/share/applications/" + n])
            for n in entries
        },
    }
    inner = {
        "commands": rows,
        "package_control_indexes": [0, 1, 2],
        "package_payload_command_index": 3,
        "package": package,
    }
    if mutation == "raw_payload":
        (evidence / "package.stdout").write_bytes(payload + b"unbound bytes")
    elif mutation == "binary_record":
        package["binary_sha256"] = "b" * 64
    elif mutation == "menu_record":
        package["entries"]["sinter.desktop"]["sha256"] = "b" * 64
    elif mutation == "control":
        rows[0]["stdout"] = menu.stream_record(io.BytesIO(b"other\n"))
    elif mutation == "index_bool":
        inner["package_payload_command_index"] = True
    elif mutation == "stream_hash":
        extracted["stdout"]["sha256"] = "b" * 64
    if mutation is None:
        contract.validate_package_payload(
            tmp_path, inner, {"installer_name": "fictional.deb"}, {"version": version}
        )
    else:
        with pytest.raises(ValueError):
            contract.validate_package_payload(
                tmp_path,
                inner,
                {"installer_name": "fictional.deb"},
                {"version": version},
            )


@pytest.mark.skipif(
    not hasattr(__import__("os"), "mkfifo"), reason="POSIX FIFO artifact fixture"
)
def test_special_profile_artifact_refuses_without_reading_fifo(tmp_path):
    import os

    path = tmp_path / "unlisted.fifo"
    os.mkfifo(path)
    try:
        with pytest.raises(ValueError, match="Special"):
            contract.profile_artifacts(tmp_path)
    finally:
        path.unlink()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_driver_entry_failure_keeps_primary_and_attempts_manager_cleanup(
    monkeypatch, inert_playwright_api, cleanup_fails
):
    api = inert_playwright_api

    calls = []

    class Driver:
        def __enter__(self):
            raise InertBodyError("primary driver start")

        def __exit__(self, *args):
            calls.append(args[0])
            if cleanup_fails:
                raise InertCloseError("secondary driver close")

    monkeypatch.setattr(api, "sync_playwright", Driver)
    session = producer.OwnedBrowserSession("inert start")
    with pytest.raises(InertBodyError, match="primary driver start"):
        with session():
            pytest.fail("Failed driver cannot admit UI work")
    assert calls == [InertBodyError]
    assert session.driver_closed is not cleanup_fails
    assert len(session.attempts) == 1 and len(session.errors) == int(cleanup_fails)


@pytest.mark.parametrize(
    "mutation", [None, "duplicate_field", "true_absence", "extra_bytes", "bool_index"]
)
def test_filesystem_query_uses_exact_source_fixed_original_bytes(mutation):
    from tools import installed_native_menu as menu

    actual = [{"path": p, "lexists": False} for p in contract.INSTALLED_PATHS]
    raw = (json.dumps(actual, sort_keys=True) + "\n").encode()
    if mutation == "duplicate_field":
        raw = raw.replace(b'"lexists": false', b'"lexists": true, "lexists": false', 1)
    elif mutation == "true_absence":
        raw = raw.replace(b'"lexists": false', b'"lexists": true', 1)
    elif mutation == "extra_bytes":
        raw += b" \n"
    row = {
        "argv": [
            "/fixed/guest/python",
            "-B",
            "-c",
            menu.FILESYSTEM_PROBE,
            *contract.INSTALLED_PATHS,
        ],
        "pid": 123,
        "exit_code": 0,
        "owned_group_remaining": False,
        "streams_complete": True,
        "stdout": menu.stream_record(io.BytesIO(raw)),
        "stderr": menu.stream_record(io.BytesIO(b"")),
    }
    absence = {
        "paths": contract.INSTALLED_PATHS,
        "command_index": False if mutation == "bool_index" else 0,
    }
    if mutation is None:
        contract.validate_absence(absence, [row])
    else:
        with pytest.raises(ValueError):
            contract.validate_absence(absence, [row])


@pytest.mark.parametrize(
    "kind", ["known", "unknown", "oversize", "not_reaped", "linked"]
)
def test_owned_temp_cleanup_retains_inventory_and_refuses_unknowns(tmp_path, kind):
    temporary = tmp_path / "t"
    temporary.mkdir()
    cache = temporary / "com.google.Chrome.chrome_chrome_url_fetcher_.abc123"
    cache.mkdir()
    path = cache / producer.CACHE_NAME
    path.write_bytes(b"inert cache bytes" if kind != "oversize" else b"x" * 32769)
    if kind == "unknown":
        (temporary / "unknown-input").write_bytes(b"must remain untouched")
    if kind == "linked":
        other = tmp_path / "outside"
        other.write_bytes(b"must remain untouched")
        path.unlink()
        try:
            path.symlink_to(other)
        except OSError:
            pytest.skip("Host cannot create symlink artifact")
    browser = {"temporary_directory": str(temporary)}
    host = {
        "pid": 123,
        "exit_code": 0,
        "owned_group_remaining": kind == "not_reaped",
        "streams_complete": True,
    }
    if kind == "known":
        producer.clean_browser_temp(tmp_path, host, browser)
        assert not any(temporary.iterdir())
        contract.validate_browser_temp(browser["temporary_cleanup"])
        assert browser["temporary_cleanup"]["inventory"][
            path.relative_to(temporary).as_posix()
        ]["sha256"] == contract.sha(b"inert cache bytes")
    else:
        with pytest.raises(ValueError):
            producer.clean_browser_temp(tmp_path, host, browser)
        assert path.exists() and browser["temporary_cleanup"]["complete"] is False
        if kind == "unknown":
            assert (
                temporary / "unknown-input"
            ).read_bytes() == b"must remain untouched"
        if kind == "linked":
            assert other.read_bytes() == b"must remain untouched"


def test_empty_owned_temp_needs_no_deletion_after_completed_collector(tmp_path):
    (tmp_path / "t").mkdir()
    browser = {"temporary_directory": str(tmp_path / "t")}
    producer.clean_browser_temp(
        tmp_path,
        {
            "pid": 123,
            "exit_code": 0,
            "owned_group_remaining": False,
            "streams_complete": True,
        },
        browser,
    )
    contract.validate_browser_temp(browser["temporary_cleanup"])
    assert (
        browser["temporary_cleanup"]["inventory"] == {}
        and browser["temporary_cleanup"]["outcomes"] == []
    )


def test_multiple_cache_removal_faults_retain_every_actual_outcome(
    tmp_path, monkeypatch
):
    temporary = tmp_path / "t"
    temporary.mkdir()
    for suffix in ("abc123", "def456"):
        directory = temporary / (
            "com.google.Chrome.chrome_chrome_url_fetcher_." + suffix
        )
        directory.mkdir()
        (directory / producer.CACHE_NAME).write_bytes(b"inert cache")
    original = type(temporary).unlink

    def unlink(path, *args, **kwargs):
        if path.name == producer.CACHE_NAME:
            raise PermissionError("inert file close refusal")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(temporary), "unlink", unlink)
    browser = {"temporary_directory": str(temporary)}
    host = {
        "pid": 123,
        "exit_code": 0,
        "owned_group_remaining": False,
        "streams_complete": True,
    }
    with pytest.raises(PermissionError, match="inert file"):
        producer.clean_browser_temp(tmp_path, host, browser)
    result = browser["temporary_cleanup"]
    assert len(result["inventory"]) == 4 and len(result["outcomes"]) == 4
    assert all(row["removed"] is False and "error" in row for row in result["outcomes"])
    assert (
        result["complete"] is False and result["failure"]["type"] == "PermissionError"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "default",
        "exit_bool",
        "exit_zero",
        "exit_negative",
        "exit_130",
        "exit_none",
        "missing_pid",
        "missing_exit",
        "missing_group",
        "remaining_group",
        "forced",
        "error",
        "missing_complete",
        "incomplete",
        "missing_stdout",
        "missing_stderr",
        "missing_passed",
        "truncated",
        "passed",
        "expected_bool",
        "expected_negative",
        "expected_130",
        "expected_none",
        "unknown_cache",
    ],
)
def test_failed_collector_cache_cleanup_refuses_unobserved_or_unsafe_rows(
    tmp_path, mutation
):
    temporary = tmp_path / "t"
    temporary.mkdir()
    cache = temporary / "com.google.Chrome.chrome_chrome_url_fetcher_.abc123"
    cache.mkdir()
    path = cache / producer.CACHE_NAME
    path.write_bytes(b"SOURCE cache must remain on refusal")
    browser = {"temporary_directory": str(temporary)}
    host = synthetic_command_row(
        ["SOURCE failed collector"], stderr=b"SOURCE failure\n"
    )
    host.update(exit_code=1, passed=False)
    expected = 1
    changes = {
        "exit_bool": ("exit_code", True),
        "exit_zero": ("exit_code", 0),
        "exit_negative": ("exit_code", -1),
        "exit_130": ("exit_code", 130),
        "exit_none": ("exit_code", None),
        "remaining_group": ("owned_group_remaining", True),
        "forced": ("forced_cleanup", True),
        "error": ("capture_error", "SOURCE retained failure"),
        "incomplete": ("streams_complete", False),
        "passed": ("passed", True),
    }
    if mutation in changes:
        key, value = changes[mutation]
        host[key] = value
    missing = {
        "missing_pid": "pid",
        "missing_exit": "exit_code",
        "missing_group": "owned_group_remaining",
        "missing_complete": "streams_complete",
        "missing_stdout": "stdout",
        "missing_stderr": "stderr",
        "missing_passed": "passed",
    }
    if mutation in missing:
        del host[missing[mutation]]
    if mutation == "truncated":
        from tools.installed_native_menu import stream_record

        host["stderr"] = stream_record(io.BytesIO(b"x" * 65_537))
    if mutation.startswith("expected_"):
        expected = {
            "expected_bool": True,
            "expected_negative": -1,
            "expected_130": 130,
            "expected_none": None,
        }[mutation]
    if mutation == "unknown_cache":
        (temporary / "unknown").write_bytes(b"SOURCE unknown must remain")
    before = copy.deepcopy(host)
    with pytest.raises((ValueError, KeyError)):
        if mutation == "default":
            producer.clean_browser_temp(tmp_path, host, browser)
        else:
            producer.clean_browser_temp(tmp_path, host, browser, expected_exit=expected)
    assert (
        host == before and path.read_bytes() == b"SOURCE cache must remain on refusal"
    )
    assert browser["temporary_cleanup"]["complete"] is False
    assert browser["temporary_cleanup"]["outcomes"] == []
    if mutation == "unknown_cache":
        assert (temporary / "unknown").read_bytes() == b"SOURCE unknown must remain"


def test_explicit_completed_failure_cleanup_preserves_first_failure_and_host(tmp_path):
    from tools.rc4_installed_workflow import Attempts

    (tmp_path / "t").mkdir()
    browser = {"temporary_directory": str(tmp_path / "t")}
    host = synthetic_command_row(
        ["SOURCE failed collector"], stderr=b"SOURCE failure\n"
    )
    host.update(exit_code=1, passed=False)
    before = copy.deepcopy(host)
    first = RuntimeError("SOURCE original workflow failure")
    attempts = Attempts(first)
    attempts.call(
        "completed collector cache",
        lambda: producer.clean_browser_temp(tmp_path, host, browser, expected_exit=1),
    )
    contract.validate_browser_temp(browser["temporary_cleanup"])
    assert browser["temporary_cleanup"]["inventory"] == {}
    assert browser["temporary_cleanup"]["outcomes"] == []
    assert host == before and host["passed"] is False and attempts.errors == []
    with pytest.raises(RuntimeError) as raised:
        attempts.raise_first()
    assert raised.value is first


BUILD_PROGRESS = [
    b"Waiting for an available worker\n",
    b"Starting\n",
    b"Indexing the supplied text locally; nothing is being uploaded\n",
    *(f"Reading document {n} of 3\n".encode("ascii") for n in range(1, 4)),
    *([b"Matching a question to exact passages, including surrounding wording\n"] * 3),
    b"Validating citations and recording retrieval coverage\n",
    b"Ready for review\n",
]


@pytest.mark.parametrize(
    "raw",
    [
        BUILD_PROGRESS[-1],
        BUILD_PROGRESS[0] + BUILD_PROGRESS[-1],
        BUILD_PROGRESS[1] + BUILD_PROGRESS[4] + b"".join(BUILD_PROGRESS[-2:]),
        b"".join(BUILD_PROGRESS),
    ],
)
def test_sampled_build_progress_admits_only_ordered_source_trace(raw):
    contract.validate_cli_stderr("casebooks.build", raw, "/fixed/export.json")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"Starting\n",
        b"Ready for review",
        b"Ready for review\n\n",
        b"Ready for review\r\n",
        b"Ready for review\nSaved: other\n",
        b"\xff diagnostic\nReady for review\n",
        "Unexpected café 🐝\nReady for review\n".encode("utf-8"),
        b"Reading document 4 of 3\nReady for review\n",
        b"Reading document 1 of 4\nReady for review\n",
        b"Reading document 2 of 3\nReading document 1 of 3\nReady for review\n",
        b"Starting\nWaiting for an available worker\nReady for review\n",
        b"Ready for review\nReady for review\n",
        BUILD_PROGRESS[6] * 4 + BUILD_PROGRESS[-1],
    ],
)
def test_build_progress_refuses_extra_reordered_incomplete_or_nonutf8_bytes(raw):
    with pytest.raises(ValueError):
        contract.validate_cli_stderr("casebooks.build", raw, "/fixed/export.json")


@pytest.mark.parametrize("operation", ["casebooks.get", "casebooks.validate"])
def test_local_readers_keep_empty_diagnostic_contract(operation):
    contract.validate_cli_stderr(operation, b"", "/fixed/export.json")
    with pytest.raises(ValueError):
        contract.validate_cli_stderr(
            operation, b"Ready for review\n", "/fixed/export.json"
        )


def test_export_progress_binds_exact_utf8_output_and_line_boundary():
    exported = "/fixed/café-é-🐝.json"
    raw = ("Saved: " + exported + "\n").encode("utf-8")
    contract.validate_cli_stderr("export", raw, exported)
    for altered in (raw + b"\n", raw[:-1], raw.replace(b".json", b".txt"), b"\xff"):
        with pytest.raises(ValueError):
            contract.validate_cli_stderr("export", altered, exported)
    for path in ("", "/bad\npath", "/bad\x00path", "🐝" * 129):
        with pytest.raises(ValueError):
            contract.validate_cli_stderr("export", raw, path)
    with pytest.raises(ValueError):
        contract.validate_cli_stderr("unknown", b"", exported)
    with pytest.raises(ValueError):
        contract.validate_cli_stderr("casebooks.get", "", exported)


def source_cli_exchange(tmp_path, monkeypatch, mutate=None, *, projection=False):
    """Inert complete CLI streams; no process or installed operation is executed."""
    from tools import installed_native_menu as menu
    from tools.rc4_scoped_recovery_contract import TITLE, wrappers

    lifecycle, before = scoped_lifecycle(tmp_path)
    monkeypatch.setattr(producer, "CLI_EXPORT_PRIVATE", tmp_path / "private-exports")
    # Actual descriptor tests remain POSIX-only. Pure Linux receipt projection
    # keeps semantic/parser fixtures portable without claiming Windows modes.
    producer.CLI_EXPORT_PRIVATE.mkdir(mode=0o700)
    if projection or os.name != "posix":
        # Pure Linux receipt projection only, not Windows descriptor/mode evidence.
        def fresh(run, output, *, cleanup):
            source, proof = producer.cli_export_paths(run, output)
            assert not source.exists() and not proof.exists()
            cleanup.extend({"fd": n, "closed": True, "failure": None} for n in (10, 11))

        def publish(run, output, document, *, cleanup):
            source, proof = producer.cli_export_paths(run, output)
            raw = source.read_bytes()
            assert contract.equal(contract.json_object(raw), document)
            proof.write_bytes(raw)
            original = {
                "st_dev": 1,
                "st_ino": 10,
                "st_uid": 0,
                "st_gid": 0,
                "st_mode": 0o100600,
                "st_nlink": 1,
                "st_size": len(raw),
                "st_mtime_ns": 20,
                "st_ctime_ns": 30,
            }
            copied = dict(original, st_ino=11, st_mode=0o100444)
            cleanup.extend(
                {"fd": n, "closed": True, "failure": None} for n in (10, 11, 12, 13)
            )
            return {
                "schema": contract.EXPORT_PROOF_SCHEMA,
                "source_path": str(source),
                "proof_path": str(proof),
                "source_before": original,
                "source_after": dict(original),
                "proof_metadata": copied,
                "bytes": len(raw),
                "sha256": contract.sha(raw),
            }

        monkeypatch.setattr(producer, "fresh_cli_export", fresh)
        monkeypatch.setattr(producer, "publish_cli_export", publish)
    stored = next(
        row
        for row in wrappers(before, "casebooks_scoped_v2")
        if row["document"]["title"] == TITLE
    )
    called = []

    def command(argv, rows, **kw):
        argv = list(map(str, argv))
        operation = "export" if argv[1] == "export" else argv[2]
        called.append(operation)
        exported = producer.CLI_EXPORT_PRIVATE / "run-1.cli-export.json"
        result = {
            "casebooks.get": stored,
            "casebooks.validate": {"document": stored["document"]},
            "casebooks.build": {
                "question_scopes": stored["document"]["question_scopes"]
            },
            "export": {"exported": str(exported), "kind": "casebook", "format": "json"},
        }[operation]
        envelope = {
            "schema": "sinter-operation-result/v1",
            "version": "fictional-version",
            "operation": "casebooks.get" if operation == "export" else operation,
            "ok": True,
            "result": result,
        }
        stderr = (
            BUILD_PROGRESS[-1]
            if operation == "casebooks.build"
            else ("Saved: " + str(exported) + "\n").encode("utf-8")
            if operation == "export"
            else b""
        )
        code = 0
        if mutate:
            code, stderr = mutate(operation, envelope, None, code, stderr)
        raw = (contract.canonical(envelope) + "\n").encode("utf-8")
        row = synthetic_command_row(argv, stdout=raw, stderr=stderr)
        if mutate:
            mutate(operation, envelope, row, code, stderr)
        rows.append(row)
        for name, path in kw["save_streams"].items():
            path.write_bytes(raw if name == "stdout" else stderr)
            row[name + "_file"] = str(path)
        if operation == "export":
            from sinter.outputs import atomic_write_text

            atomic_write_text(exported, contract.canonical(stored["document"]))
        return code, raw

    monkeypatch.setattr(menu, "command", command)
    return lifecycle, before, called


def final_cli_data(lifecycle):
    """Use the fixed installed paths in a finite source-only verifier fixture."""
    from tools import installed_native_menu as menu

    data = {
        path.relative_to(lifecycle.output).as_posix(): path.read_bytes()
        for path in lifecycle.output.rglob("*")
        if path.is_file()
    }
    receipt = contract.json_object(data["process/run-1.cli.json"])
    for operation, row in receipt["operations"].items():
        prefix = "process/run-1." + operation.replace(".", "-")
        row["argv"] = [
            "/out/evidence/scoped/"
            + Path(part).relative_to(lifecycle.output).as_posix()
            if Path(part).is_relative_to(lifecycle.output)
            else "/out/runtime/scoped/data"
            if part == str(lifecycle.runtime / "data")
            else contract.EXPORT_PRIVATE + "/" + Path(part).name
            if Path(part).is_relative_to(producer.CLI_EXPORT_PRIVATE)
            else part
            for part in row["argv"]
        ]
        if operation == "export":
            data[prefix + ".stderr"] = (
                b"Saved: /tmp/sinter-rc4-cli-exports/run-1.cli-export.json\n"
            )
            row["stderr"] = menu.stream_record(io.BytesIO(data[prefix + ".stderr"]))
        for name in ("stdout", "stderr"):
            row[name + "_file"] = "/out/evidence/scoped/" + prefix + "." + name
    publication = receipt["export_proof"]
    publication["source_path"] = contract.EXPORT_PRIVATE + "/run-1.cli-export.json"
    publication["proof_path"] = "/out/evidence/scoped/process/run-1.cli-export.json"
    # Explicit structural projection only; this fixture never claims container UID0.
    for name in ("source_before", "source_after", "proof_metadata"):
        publication[name]["st_uid"] = publication[name]["st_gid"] = 0
    data["process/run-1.cli.json"] = contract.canonical(receipt).encode("utf-8")
    return data


@pytest.mark.parametrize(
    "projection", [False, True], ids=["posix-descriptors", "inert-portable"]
)
def test_complete_source_cli_progress_and_export_pass_both_admission_boundaries(
    tmp_path, monkeypatch, projection
):
    if os.name != "posix" and not projection:
        pytest.skip("Actual Linux proof descriptors are not a Windows qualification.")
    if projection:

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "Portable fixture must not open Linux proof descriptors."
            )

        monkeypatch.setattr(producer, "export_directory", forbidden)
    lifecycle, before, called = source_cli_exchange(
        tmp_path, monkeypatch, projection=projection
    )
    lifecycle.cli_readers(1, before)
    assert called == [
        "casebooks.get",
        "casebooks.validate",
        "casebooks.build",
        "export",
    ]
    result = producer.read_json(lifecycle.output / "process/run-1.cli.json")
    assert contract.equal(result["before"], result["after"])
    raw = (lifecycle.output / "process/run-1.casebooks-build.stderr").read_bytes()
    assert raw == b"Ready for review\n"
    contract.validate_cli(final_cli_data(lifecycle), 1, before, "fictional-version")


def test_real_offline_dispatcher_progress_export_and_scoped_inputs_are_preserved(
    tmp_path,
):
    from sinter import __version__
    from sinter.casebooks import Casebooks, validate
    from sinter.store import Store
    from tools import rc4_scoped_recovery_contract as scoped
    from tools import rc4_scoped_recovery_worker as worker
    from tools.rc4_recovery_worker import seed, snapshot

    root = tmp_path / "fictional café é 🐝"
    root.mkdir()
    data = root / "data"
    seed(data)
    book = validate(scoped.fixture())
    book = validate(
        {
            **book,
            "schema": "sinter-casebook/v2",
            "question_scopes": [
                {
                    "question_index": i,
                    "question": question,
                    "source_ids": [book["documents"][i]["id"]],
                }
                for i, question in enumerate(scoped.QUESTIONS)
            ],
        }
    )
    saved = Casebooks(Store(data)).save(book)
    before = snapshot(data)
    for operation in (
        "casebooks.get",
        "casebooks.validate",
        "casebooks.build",
        "export",
    ):
        payload = root / (operation.replace(".", "-") + ".input.json")
        body = (
            {"document": book}
            if operation == "casebooks.validate"
            else {"id": saved["id"]}
        )
        if operation == "casebooks.build":
            body["revision"] = saved["revision"]
        producer.write_json(payload, body)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-X",
                "utf8",
                str(worker.__file__),
                "--cli-child",
                str(producer.ROOT),
                str(data),
                operation,
                str(payload),
            ],
            env=worker.cli_reader_environment(root / "home"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            check=False,
        )
        (root / (operation + ".stdout")).write_bytes(result.stdout)
        (root / (operation + ".stderr")).write_bytes(result.stderr)
        assert result.returncode == 0
        envelope = contract.json_object(result.stdout)
        assert envelope["schema"] == "sinter-operation-result/v1"
        assert envelope["version"] == __version__ and envelope["ok"] is True
        assert envelope["operation"] == (
            "casebooks.get" if operation == "export" else operation
        )
        exported = payload.with_name(
            payload.name.replace(".input.json", ".cli-export.json")
        )
        # Qualification is Linux-only. The source dispatcher uses the native
        # platform print separator; retain those raw bytes before this fixture
        # projection.
        diagnostic = (
            result.stderr.replace(b"\r\n", b"\n") if os.name == "nt" else result.stderr
        )
        contract.validate_cli_stderr(operation, diagnostic, str(exported))
        if operation == "casebooks.build":
            assert diagnostic.endswith(b"Ready for review\n")
            assert contract.equal(
                envelope["result"]["question_scopes"], book["question_scopes"]
            )
        if operation == "export":
            assert diagnostic == ("Saved: " + str(exported) + "\n").encode("utf-8")
            assert contract.equal(producer.read_json(exported), book)
        assert contract.equal(snapshot(data), before)


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "operation",
        "version",
        "ok",
        "nonzero",
        "bool_code",
        "group",
        "forced",
        "incomplete",
        "stdout_hash",
        "stderr_hash",
        "diagnostic",
        "invalid_utf8",
    ],
)
def test_source_cli_refuses_identity_exit_capture_or_diagnostics_before_next_reader(
    tmp_path, monkeypatch, mutation
):
    def mutate(operation, envelope, row, code, stderr):
        if operation != "casebooks.get":
            return code, stderr
        if row is None:
            if mutation in {"schema", "operation", "version"}:
                envelope[mutation] = "wrong"
            elif mutation == "ok":
                envelope["ok"] = False
            elif mutation == "nonzero":
                code = 1
            elif mutation == "bool_code":
                code = False
            elif mutation == "diagnostic":
                stderr = b"Ready for review\n"
            elif mutation == "invalid_utf8":
                stderr = b"\xff diagnostic\n"
        elif mutation in {"group", "forced", "incomplete"}:
            field = {
                "group": "owned_group_remaining",
                "forced": "forced_cleanup",
                "incomplete": "streams_complete",
            }[mutation]
            row[field] = mutation != "incomplete"
        elif mutation in {"stdout_hash", "stderr_hash"}:
            row[mutation.split("_")[0]]["sha256"] = "0" * 64
        elif mutation == "nonzero":
            row["exit_code"] = 1
        return code, stderr

    lifecycle, before, called = source_cli_exchange(tmp_path, monkeypatch, mutate)
    with pytest.raises(ValueError):
        lifecycle.cli_readers(1, before)
    assert called == ["casebooks.get"]
    result = producer.read_json(lifecycle.output / "process/run-1.cli.json")
    assert result["after"] is None and set(result["operations"]) == {"casebooks.get"}
    assert (lifecycle.output / "process/run-1.casebooks-get.stdout").is_file()
    assert (lifecycle.output / "process/run-1.casebooks-get.stderr").is_file()


@pytest.mark.parametrize("operation", ["casebooks.build", "export"])
@pytest.mark.parametrize("diagnostic", [b"extra\n", b"\xff diagnostic\n"])
def test_final_cli_contract_rejects_retained_extra_or_invalid_diagnostics(
    tmp_path, monkeypatch, operation, diagnostic
):
    from tools import installed_native_menu as menu

    lifecycle, before, _ = source_cli_exchange(tmp_path, monkeypatch)
    lifecycle.cli_readers(1, before)
    data = final_cli_data(lifecycle)
    receipt = contract.json_object(data["process/run-1.cli.json"])
    prefix = "process/run-1." + operation.replace(".", "-")
    data[prefix + ".stderr"] += diagnostic
    receipt["operations"][operation]["stderr"] = menu.stream_record(
        io.BytesIO(data[prefix + ".stderr"])
    )
    data["process/run-1.cli.json"] = contract.canonical(receipt).encode("utf-8")
    with pytest.raises(ValueError):
        contract.validate_cli(data, 1, before, "fictional-version")


@pytest.mark.parametrize("stop_fault", [False, True])
def test_failed_lifecycle_reaps_ownership_without_replaying_cli_or_overwriting_proof(
    tmp_path, monkeypatch, stop_fault
):
    from tools import native_window_smoke as native

    runtime, output = exchange(tmp_path, "scoped")
    paths = {name: output / f"process/run-1.{name}" for name in ("stdout", "stderr")}
    paths["stdout"].write_bytes(b"SOURCE app stdout\n")
    paths["stderr"].write_bytes(b"")
    streams = [paths[name].open("ab") for name in ("stdout", "stderr")]
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.profile = runtime, output, "scoped"
    lifecycle.paths, lifecycle.streams, lifecycle.notice = paths, streams, b""
    lifecycle.rows = [{"run": 1, "pid": 4321, "stop_method": "interface_quit"}]
    lifecycle.identity = {"version": "SOURCE"}
    lifecycle.process = SimpleNamespace(poll=lambda: 0)
    lifecycle.failure, lifecycle.closed = None, False
    events, reader_pins = [], {}
    primary = ValueError("SOURCE first reader refusal")
    lifecycle.launch = lambda run: events.append(("launch", run))
    lifecycle.admission = lambda label: {"unchanged": True}
    lifecycle.rpc = SimpleNamespace(service=lambda: events.append("rpc"))
    lifecycle.thread = SimpleNamespace(
        start=lambda: events.append("thread start"),
        join=lambda **kw: events.append(("thread join", kw)),
        is_alive=lambda: False,
    )
    lifecycle.inner = SimpleNamespace(
        port=1,
        shutdown=lambda: events.append("shutdown"),
        server_close=lambda: events.append("server close"),
        idle=lambda: True,
    )

    def stop(process, row):
        events.append("stop")
        row.update(forced_cleanup=False, owned_group_remaining=False)
        if stop_fault and events.count("stop") == 2:
            raise RuntimeError("SOURCE later stop fault")

    def reader(run, before):
        events.append("reader")
        path = output / "process/run-1.cli.json"
        raw_path = output / "process/run-1.casebooks-build.stderr"
        if events.count("reader") > 1:
            path.write_bytes(b"SOURCE overwritten original")
            raise FileExistsError("SOURCE replay must never occur")
        path.write_bytes(b"SOURCE original first CLI receipt\n")
        raw_path.write_bytes(b"Ready for review\n")
        reader_pins.update({path: path.read_bytes(), raw_path: raw_path.read_bytes()})
        raise primary

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, timeout):
            assert timeout == 1

        def connect_ex(self, target):
            assert target == ("127.0.0.1", 1)
            return 111

    lifecycle.cli_readers = reader
    monkeypatch.setattr(native, "stop_process", stop)
    monkeypatch.setattr(producer.socket, "socket", Probe)
    monkeypatch.setattr(producer, "fixed_snapshot", lambda path: {"unchanged": True})
    lifecycle.run()
    assert events.count("reader") == 1 and events.count("stop") == 2
    assert all(path.read_bytes() == raw for path, raw in reader_pins.items())
    row = producer.read_json(output / "process/run-1.json")
    cleanup = producer.read_json(output / "process/run-1.cleanup.json")
    assert row == cleanup and row["stop_method"] == "interface_quit"
    assert row["returncode"] == 0 and row["owned_group_remaining"] is False
    assert all(stream.closed for stream in streams)
    assert "shutdown" in events and "server close" in events
    assert ("thread join", {"timeout": 5}) in events
    state = producer.read_json(runtime / "state.json")
    first_failure = "ValueError: observation: " + str(primary)
    assert state == {"phase": "failed", "failure": first_failure}
    result = producer.read_json(output / "processes.json")
    assert result["closed"] is True and result["failure"].startswith(first_failure)
    if stop_fault:
        assert "SOURCE later stop fault" in result["failure"]
    else:
        assert "cleanup:" not in result["failure"]


def test_cleanup_stop_and_stream_faults_still_attempt_all_capture_without_readers(
    tmp_path, monkeypatch
):
    from tools import native_window_smoke as native
    from tools import rc4_recovery_source as source

    runtime, output = exchange(tmp_path, "scoped")
    paths = {name: output / f"process/run-1.{name}" for name in ("stdout", "stderr")}
    for name, path in paths.items():
        path.write_bytes(("SOURCE " + name + "\n").encode("ascii"))
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.profile = runtime, output, "scoped"
    lifecycle.paths, lifecycle.notice = paths, b""
    lifecycle.process = SimpleNamespace(poll=lambda: 0)
    lifecycle.rows = [{"run": 1, "pid": 4321, "stop_method": "interface_quit"}]
    events = []

    def stop(*args):
        events.append("stop")
        raise RuntimeError("SOURCE first stop fault")

    class Stream:
        def __init__(self, name):
            self.name = name

        def close(self):
            events.append("close " + self.name)
            raise OSError("SOURCE close " + self.name)

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, timeout):
            pass

        def connect_ex(self, target):
            events.append("port")
            return 111

    original_capture = source.capture_stream

    def capture(path):
        events.append("capture " + path.suffix[1:])
        if path.suffix == ".stderr":
            raise OSError("SOURCE stderr capture fault")
        return original_capture(path)

    def forbidden(*args):
        raise AssertionError("Cleanup must never replay optional admissions")

    lifecycle.streams = [Stream(name) for name in ("stdout", "stderr")]
    lifecycle.inner = SimpleNamespace(port=1)
    lifecycle.admission = lifecycle.cli_readers = forbidden
    monkeypatch.setattr(producer, "fixed_snapshot", forbidden)
    monkeypatch.setattr(native, "stop_process", stop)
    monkeypatch.setattr(producer.socket, "socket", Probe)
    monkeypatch.setattr(source, "capture_stream", capture)
    with pytest.raises(ValueError) as raised:
        lifecycle.reap(1, observe=False)
    assert str(raised.value) == (
        "stop: SOURCE first stop fault; stream close: SOURCE close stdout; "
        "stream close: SOURCE close stderr; stderr capture: SOURCE stderr capture fault"
    )
    assert events == [
        "stop",
        "close stdout",
        "close stderr",
        "capture stderr",
        "capture stdout",
        "port",
    ]
    row = producer.read_json(output / "process/run-1.cleanup.json")
    assert row["stdout"]["sha256"] == contract.sha(paths["stdout"].read_bytes())
    assert not (output / "process/run-1.json").exists()
    assert not (runtime / "state.json").exists()


@pytest.mark.parametrize("held", [False, True])
def test_failed_host_cleanup_requires_held_normal_failure_and_does_not_promote(
    tmp_path, held
):
    (tmp_path / "t").mkdir()
    browser = {"temporary_directory": str(tmp_path / "t")}
    host = synthetic_command_row(["SOURCE host"], stderr=b"SOURCE failure\n")
    host.update(exit_code=1, passed=False)
    before = copy.deepcopy(host)
    if held:
        producer.cleanup_browser_after_host(tmp_path, host, browser, failed=True)
        contract.validate_browser_temp(browser["temporary_cleanup"])
        assert browser["temporary_cleanup"]["complete"] is True
    else:
        with pytest.raises(ValueError):
            producer.cleanup_browser_after_host(tmp_path, host, browser, failed=False)
    assert host == before and host["passed"] is False


@pytest.mark.parametrize("code", [True, -1, 130, None])
def test_failed_host_cleanup_refuses_unknown_signal_and_bool_outcomes(tmp_path, code):
    (tmp_path / "t").mkdir()
    browser = {"temporary_directory": str(tmp_path / "t")}
    host = synthetic_command_row(["SOURCE host"], stderr=b"SOURCE failure\n")
    host.update(exit_code=code, passed=False)
    before = copy.deepcopy(host)
    with pytest.raises(ValueError):
        producer.cleanup_browser_after_host(tmp_path, host, browser, failed=True)
    assert host == before and browser["temporary_cleanup"]["complete"] is False


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
@pytest.mark.parametrize("size", [0, 524_288])
def test_private_top_level_temp_shape_has_complete_original_metadata(tmp_path, size):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    path = temporary / ".org.chromium.Chromium.Abc123"
    raw = b"x" * size
    path.write_bytes(raw)
    path.chmod(0o600)
    before = producer.browser_temp_metadata(path.lstat())
    browser = {"temporary_directory": str(temporary)}
    host = synthetic_command_row(["SOURCE stopped collector"])
    producer.clean_browser_temp(tmp_path, host, browser)
    observation = browser["temporary_cleanup"]
    contract.validate_browser_temp(observation)
    assert observation["inventory"] == {
        path.name: {
            "type": "file",
            "bytes": size,
            "sha256": contract.sha(raw),
            "metadata": before,
        }
    }
    assert observation["outcomes"] == [{"path": path.name, "removed": True}]
    assert not any(temporary.iterdir()) and host["passed"] is True


def private_temp_observation():
    """Typed portable source observation, never a measured installed file."""
    name = ".org.chromium.Chromium.Abc123"
    return {
        "attempted": True,
        "complete": True,
        "failure": None,
        "inventory": {
            name: {
                "type": "file",
                "bytes": 524_288,
                "sha256": "a" * 64,
                "metadata": {
                    "dev": 1,
                    "ino": 2,
                    "mode": 0o100600,
                    "uid": os.getuid() if hasattr(os, "getuid") else 0,
                    "gid": os.getgid() if hasattr(os, "getgid") else 0,
                    "nlink": 1,
                    "size": 524_288,
                    "mtime_ns": 3,
                    "ctime_ns": 4,
                },
            }
        },
        "outcomes": [{"path": name, "removed": True}],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "suffix5",
        "suffix7",
        "suffix_dash",
        "different_prefix",
        "nested",
        "path_escape",
        "size",
        "size_bool",
        "sha",
        "extra",
        "missing_metadata",
        "mode",
        "uid",
        "gid",
        "links",
        "size_mismatch",
        "dev_zero",
        "ino_zero",
        "metadata_bool",
        "negative_time",
        "metadata_extra",
        "missing_ctime",
        "not_removed",
        "unknown_entry",
        "over64",
        "legacy_oversize",
    ],
)
def test_private_temp_contract_closed_shape_and_original_legacy_bound(mutation):
    observed = private_temp_observation()
    name = next(iter(observed["inventory"]))
    row = observed["inventory"][name]
    metadata = row["metadata"]
    names = {
        "suffix5": ".org.chromium.Chromium.Abc12",
        "suffix7": ".org.chromium.Chromium.Abc1234",
        "suffix_dash": ".org.chromium.Chromium.Ab-123",
        "different_prefix": ".org.chromium.Chrome.Abc123",
        "nested": "folder/" + name,
        "path_escape": "../" + name,
    }
    if mutation in names:
        changed = names[mutation]
        observed["inventory"] = {changed: row}
        observed["outcomes"][0]["path"] = changed
    elif mutation == "size":
        row["bytes"] = metadata["size"] = 524_289
    elif mutation == "size_bool":
        row["bytes"] = True
    elif mutation == "sha":
        row["sha256"] = "unknown"
    elif mutation == "extra":
        row["provenance"] = "Chromium"
    elif mutation == "missing_metadata":
        del row["metadata"]
    elif mutation in {
        "mode",
        "uid",
        "gid",
        "links",
        "size_mismatch",
        "dev_zero",
        "ino_zero",
        "metadata_bool",
        "negative_time",
    }:
        field, value = {
            "mode": ("mode", 0o100644),
            "uid": ("uid", metadata["uid"] + 1),
            "gid": ("gid", metadata["gid"] + 1),
            "links": ("nlink", 2),
            "size_mismatch": ("size", 0),
            "dev_zero": ("dev", 0),
            "ino_zero": ("ino", 0),
            "metadata_bool": ("mtime_ns", True),
            "negative_time": ("ctime_ns", -1),
        }[mutation]
        metadata[field] = value
    elif mutation == "metadata_extra":
        metadata["atime_ns"] = 0
    elif mutation == "missing_ctime":
        del metadata["ctime_ns"]
    elif mutation == "not_removed":
        observed["outcomes"][0]["removed"] = False
    elif mutation == "unknown_entry":
        observed["inventory"]["private-but-unknown"] = copy.deepcopy(row)
    elif mutation == "over64":
        observed["inventory"] = {
            f".org.chromium.Chromium.{n:06d}": copy.deepcopy(row) for n in range(65)
        }
    elif mutation == "legacy_oversize":
        observed["inventory"] = {
            "com.google.Chrome.chrome_chrome_url_fetcher_.abc123": {
                "type": "directory",
                "bytes": 4096,
            },
            "com.google.Chrome.chrome_chrome_url_fetcher_.abc123/"
            + producer.CACHE_NAME: {
                "type": "file",
                "bytes": 32769,
                "sha256": "a" * 64,
            },
        }
    if mutation is None:
        contract.validate_browser_temp(observed)
    else:
        with pytest.raises(ValueError):
            contract.validate_browser_temp(observed)


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "oversize",
        "mode",
        "root_mode",
        "hardlink",
        "symlink",
        "special",
        "live_group",
        "incomplete",
        "missing_stdout",
        "bad_stderr",
        "directory_shape",
        "over64",
    ],
)
def test_private_temp_inventory_refusal_deletes_nothing(tmp_path, mutation):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    path = temporary / ".org.chromium.Chromium.Abc123"
    path.write_bytes(b"SOURCE private cache")
    path.chmod(0o600)
    host = synthetic_command_row(["SOURCE stopped collector"])
    browser = {"temporary_directory": str(temporary)}
    if mutation == "unknown":
        (temporary / "unknown").write_bytes(b"must remain")
    elif mutation == "oversize":
        path.write_bytes(b"x" * 524_289)
    elif mutation == "mode":
        path.chmod(0o644)
    elif mutation == "root_mode":
        temporary.chmod(0o755)
    elif mutation == "hardlink":
        os.link(path, tmp_path / "second-link")
    elif mutation == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(b"must remain")
        path.unlink()
        path.symlink_to(outside)
    elif mutation == "special":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif mutation == "live_group":
        host["owned_group_remaining"] = True
    elif mutation == "incomplete":
        host["streams_complete"] = False
    elif mutation == "missing_stdout":
        del host["stdout"]
    elif mutation == "bad_stderr":
        host["stderr"]["sha256"] = "wrong"
    elif mutation == "directory_shape":
        path.unlink()
        path.mkdir(mode=0o700)
    elif mutation == "over64":
        for n in range(64):
            another = temporary / f".org.chromium.Chromium.{n:06d}"
            another.write_bytes(b"SOURCE")
            another.chmod(0o600)
    before = sorted(p.name for p in temporary.iterdir())
    with pytest.raises(ValueError):
        producer.clean_browser_temp(tmp_path, host, browser)
    assert sorted(p.name for p in temporary.iterdir()) == before
    assert browser["temporary_cleanup"]["complete"] is False
    assert browser["temporary_cleanup"]["outcomes"] == []


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
@pytest.mark.parametrize(
    "mutation",
    [
        "bytes",
        "mode",
        "link",
        "replace",
        "directory_replace",
        "read_error",
        "unlink_error",
    ],
)
def test_private_temp_before_delete_race_and_original_failure_retained(
    tmp_path, monkeypatch, mutation
):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    path = temporary / ".org.chromium.Chromium.Abc123"
    original_bytes = b"SOURCE private cache"
    path.write_bytes(original_bytes)
    path.chmod(0o600)
    browser = {"temporary_directory": str(temporary)}
    host = synthetic_command_row(["SOURCE stopped collector"])
    original = producer.owned_browser_temp_bytes
    calls = []
    fault = OSError("SOURCE original cleanup read refusal")

    def reader(p, before):
        calls.append(str(p))
        if len(calls) == 2:
            if mutation == "bytes":
                p.write_bytes(b"changed same bytes!!")
            elif mutation == "mode":
                p.chmod(0o644)
            elif mutation == "link":
                os.link(p, tmp_path / "second-link")
            elif mutation == "replace":
                p.unlink()
                p.write_bytes(original_bytes)
                p.chmod(0o600)
            elif mutation == "read_error":
                raise fault
        return original(p, before)

    monkeypatch.setattr(producer, "owned_browser_temp_bytes", reader)
    original_lstat = type(path).lstat
    count = [0]

    def lstat(p, *args, **kwargs):
        if p == temporary:
            count[0] += 1
            if mutation == "directory_replace" and count[0] == 3:
                temporary.rename(tmp_path / "old-t")
                temporary.mkdir(mode=0o700)
                (temporary / path.name).write_bytes(original_bytes)
                (temporary / path.name).chmod(0o600)
        return original_lstat(p, *args, **kwargs)

    monkeypatch.setattr(type(path), "lstat", lstat)
    original_unlink = type(path).unlink

    def unlink(p, *args, **kwargs):
        if p == path and mutation == "unlink_error":
            raise fault
        return original_unlink(p, *args, **kwargs)

    monkeypatch.setattr(type(path), "unlink", unlink)
    with pytest.raises((ValueError, OSError)) as caught:
        producer.clean_browser_temp(tmp_path, host, browser)
    if mutation in {"read_error", "unlink_error"}:
        assert caught.value is fault
    observed = browser["temporary_cleanup"]
    assert observed["complete"] is False and path.exists()
    assert observed["inventory"][path.name]["sha256"] == contract.sha(original_bytes)
    assert observed["outcomes"][0]["removed"] is False
    assert observed["failure"]["type"] == type(caught.value).__name__


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
def test_private_temp_and_original_nested_cache_both_retained_before_cleanup(tmp_path):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    top = temporary / ".org.chromium.Chromium.Abc123"
    top.write_bytes(b"SOURCE new bounded shape")
    top.chmod(0o600)
    directory = temporary / "com.google.Chrome.chrome_chrome_url_fetcher_.abc123"
    directory.mkdir()
    nested = directory / producer.CACHE_NAME
    nested.write_bytes(b"SOURCE original cache")
    browser = {"temporary_directory": str(temporary)}
    producer.clean_browser_temp(
        tmp_path, synthetic_command_row(["SOURCE stopped collector"]), browser
    )
    observed = browser["temporary_cleanup"]
    contract.validate_browser_temp(observed)
    assert len(observed["inventory"]) == len(observed["outcomes"]) == 3
    assert set(observed["inventory"][nested.relative_to(temporary).as_posix()]) == {
        "type",
        "bytes",
        "sha256",
    }
    assert not any(temporary.iterdir())


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
@pytest.mark.parametrize("failed", [False, True])
def test_private_temp_failed_host_cleanup_is_explicit_and_never_success(
    tmp_path, failed
):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    path = temporary / ".org.chromium.Chromium.Abc123"
    path.write_bytes(b"SOURCE bounded failed-host cache")
    path.chmod(0o600)
    host = synthetic_command_row(["SOURCE failed collector"], stderr=b"held failure\n")
    host.update(exit_code=1, passed=False)
    before = copy.deepcopy(host)
    browser = {"temporary_directory": str(temporary)}
    if failed:
        producer.cleanup_browser_after_host(tmp_path, host, browser, failed=True)
        contract.validate_browser_temp(browser["temporary_cleanup"])
        assert not path.exists()
    else:
        with pytest.raises(ValueError):
            producer.cleanup_browser_after_host(tmp_path, host, browser, failed=False)
        assert path.exists() and browser["temporary_cleanup"]["outcomes"] == []
    assert host == before and host["passed"] is False


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
@pytest.mark.parametrize("field", ["st_uid", "st_gid"])
def test_private_temp_read_refuses_foreign_observed_metadata(tmp_path, field):
    path = tmp_path / ".org.chromium.Chromium.Abc123"
    path.write_bytes(b"SOURCE bytes remain")
    path.chmod(0o600)
    actual = path.lstat()
    before = SimpleNamespace(
        **{
            "st_" + key: value
            for key, value in producer.browser_temp_metadata(actual).items()
        }
    )
    setattr(before, field, getattr(before, field) + 1)
    with pytest.raises(ValueError, match="private single-link"):
        producer.owned_browser_temp_bytes(path, before)
    assert path.read_bytes() == b"SOURCE bytes remain"


@pytest.mark.skipif(
    os.name != "posix", reason="Actual private mode/ownership needs POSIX"
)
def test_private_temp_independent_removals_preserve_first_exception(
    tmp_path, monkeypatch
):
    temporary = tmp_path / "t"
    temporary.mkdir(mode=0o700)
    names = [".org.chromium.Chromium.Abc123", ".org.chromium.Chromium.Def456"]
    for name in names:
        path = temporary / name
        path.write_bytes(b"SOURCE owned bytes")
        path.chmod(0o600)
    first = OSError("SOURCE first unlink refusal")
    second = PermissionError("SOURCE later unlink refusal")
    original = type(temporary).unlink
    attempted = []

    def unlink(path, *args, **kwargs):
        if path.name in names:
            attempted.append(path.name)
            raise first if len(attempted) == 1 else second
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(temporary), "unlink", unlink)
    browser = {"temporary_directory": str(temporary)}
    with pytest.raises(OSError) as caught:
        producer.clean_browser_temp(
            tmp_path, synthetic_command_row(["SOURCE stopped"]), browser
        )
    assert caught.value is first and attempted == names
    observation = browser["temporary_cleanup"]
    assert [row["error"]["type"] for row in observation["outcomes"]] == [
        "OSError",
        "PermissionError",
    ]
    assert observation["complete"] is False and observation["failure"][
        "message"
    ] == str(first)
    assert sorted(p.name for p in temporary.iterdir()) == names


@pytest.fixture
def private_cli_export(tmp_path, monkeypatch):
    """Actual private atomic export, no CLI/app/container or provider invocation."""
    from sinter.outputs import atomic_write_text

    private = tmp_path / "container-private-exports"
    monkeypatch.setattr(producer, "CLI_EXPORT_PRIVATE", private)
    producer.prepare_cli_export_directory()
    output = tmp_path / "evidence"
    (output / "process").mkdir(parents=True)
    document = {"schema": "fictional-source-control", "original": "café é 🐝"}

    def create(run=1):
        source, proof = producer.cli_export_paths(run, output)
        producer.fresh_cli_export(run, output)
        atomic_write_text(source, json.dumps(document, ensure_ascii=False) + "\n")
        return source, proof

    return output, document, create


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
@pytest.mark.parametrize("run", [1, 2, 3, 4])
def test_private_cli_export_distinct_proof_preserves_full_bytes_and_0600(
    private_cli_export, run
):
    output, document, create = private_cli_export
    source, proof = create(run)
    before = contract.export_metadata(source.lstat())
    raw = source.read_bytes()
    value = producer.publish_cli_export(run, output, document)
    assert source.read_bytes() == proof.read_bytes() == raw
    assert contract.export_metadata(source.lstat()) == before
    assert source.stat().st_mode & 0o777 == 0o600
    assert proof.stat().st_mode & 0o777 == 0o444
    assert source.stat().st_ino != proof.stat().st_ino
    assert value["source_before"] == value["source_after"] == before
    assert value["proof_metadata"] == contract.export_metadata(proof.lstat())
    assert value["bytes"] == len(raw) and value["sha256"] == contract.sha(raw)
    with pytest.raises(ValueError, match="fresh"):
        producer.fresh_cli_export(run, output)


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
def test_private_cli_export_fixed_directory_and_index_refuse_unknown_reuse(
    private_cli_export,
):
    output, _, _ = private_cli_export
    with pytest.raises(FileExistsError):
        producer.prepare_cli_export_directory()
    for run in (False, 0, 5, -1, None, 1.0):
        with pytest.raises(ValueError, match="Unknown"):
            producer.cli_export_paths(run, output)
    assert not list((output / "process").iterdir())


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
@pytest.mark.parametrize(
    "mutation",
    [
        "symlink",
        "hardlink",
        "mode",
        "oversize",
        "wrong_document",
        "private_directory",
        "proof_exists",
    ],
)
def test_private_cli_export_unsafe_original_or_destination_refuses(
    private_cli_export, mutation
):
    output, document, create = private_cli_export
    source, proof = create()
    if mutation == "symlink":
        old = source.with_name("retained-original")
        source.rename(old)
        source.symlink_to(old)
    elif mutation == "hardlink":
        os.link(source, source.with_name("second-link"))
    elif mutation == "mode":
        source.chmod(0o644)
    elif mutation == "oversize":
        with source.open("ab") as stream:
            stream.write(b" " * producer.MAX_RPC)
    elif mutation == "wrong_document":
        source.write_bytes(b'{"other":"unrelated"}')
    elif mutation == "private_directory":
        source.parent.chmod(0o755)
    else:
        proof.write_bytes(b"existing proof must stay")
    with pytest.raises((ValueError, FileExistsError)):
        producer.publish_cli_export(1, output, document)
    if mutation == "proof_exists":
        assert proof.read_bytes() == b"existing proof must stay"
    else:
        assert not proof.exists()
    assert source.exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
def test_private_cli_export_foreign_directory_refuses_before_open(
    private_cli_export, monkeypatch
):
    output, document, create = private_cli_export
    _, proof = create()
    actual = os.geteuid()
    monkeypatch.setattr(producer.os, "geteuid", lambda: actual + 1)
    with pytest.raises(ValueError, match="directory ownership"):
        producer.publish_cli_export(1, output, document)
    assert not proof.exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
@pytest.mark.parametrize("mutation", ["source_bytes", "source_directory", "proof_path"])
def test_private_cli_export_descriptor_and_named_path_races_refuse(
    private_cli_export, monkeypatch, mutation
):
    output, document, create = private_cli_export
    source, proof = create()
    original_write = os.write
    triggered = False

    def write(fd, raw):
        nonlocal triggered
        result = original_write(fd, raw)
        if not triggered:
            triggered = True
            if mutation == "source_bytes":
                source.write_bytes(b"{}")
            elif mutation == "source_directory":
                source.parent.rename(source.parent.with_name("retained-private-root"))
                source.parent.mkdir(mode=0o700)
            else:
                proof.rename(proof.with_name("retained-first-copy"))
                proof.write_bytes(bytes(raw))
                proof.chmod(0o444)
        return result

    monkeypatch.setattr(producer.os, "write", write)
    with pytest.raises(ValueError, match="changed|identity"):
        producer.publish_cli_export(1, output, document)
    assert triggered


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
def test_private_cli_export_partial_write_retains_first_fault_and_private_original(
    private_cli_export, monkeypatch
):
    output, document, create = private_cli_export
    source, proof = create()
    raw = source.read_bytes()
    actual_write = os.write
    writes = []

    def write(fd, data):
        writes.append(len(data))
        if len(writes) == 1:
            return actual_write(fd, data[:3])
        raise OSError("first proof publication fault")

    monkeypatch.setattr(producer.os, "write", write)
    with pytest.raises(OSError, match="first proof publication fault"):
        producer.publish_cli_export(1, output, document)
    assert proof.read_bytes() == raw[:3]
    assert source.read_bytes() == raw and source.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="fresh"):
        producer.fresh_cli_export(1, output)


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
def test_source_cli_export_publication_fault_preserves_capture_and_stops_run(
    tmp_path, monkeypatch
):
    lifecycle, before, called = source_cli_exchange(tmp_path, monkeypatch)

    def failed(*args, **kwargs):
        raise OSError("first export proof fault")

    monkeypatch.setattr(producer, "publish_cli_export", failed)
    with pytest.raises(OSError, match="first export proof fault"):
        lifecycle.cli_readers(1, before)
    result = producer.read_json(lifecycle.output / "process/run-1.cli.json")
    assert called == [
        "casebooks.get",
        "casebooks.validate",
        "casebooks.build",
        "export",
    ]
    assert result["export_proof"] is None and result["after"] is None
    assert result["operations"]["export"]["streams_complete"] is True
    assert contract.equal(
        result["reader_snapshots"]["export"]["before"],
        result["reader_snapshots"]["export"]["after"],
    )
    assert (
        producer.CLI_EXPORT_PRIVATE / "run-1.cli-export.json"
    ).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "mutation",
    [
        "original_changed",
        "same_inode",
        "wrong_copy_hash",
        "source_world_readable",
        "copy_writable",
        "unknown_path",
        "bool_metadata",
    ],
)
def test_final_cli_contract_rejects_export_proof_identity_or_content_mutation(
    tmp_path, monkeypatch, mutation
):
    lifecycle, before, _ = source_cli_exchange(tmp_path, monkeypatch)
    lifecycle.cli_readers(1, before)
    data = final_cli_data(lifecycle)
    receipt = contract.json_object(data["process/run-1.cli.json"])
    proof = receipt["export_proof"]
    if mutation == "original_changed":
        proof["source_after"]["st_mtime_ns"] += 1
    elif mutation == "same_inode":
        proof["proof_metadata"]["st_ino"] = proof["source_before"]["st_ino"]
        proof["proof_metadata"]["st_dev"] = proof["source_before"]["st_dev"]
    elif mutation == "wrong_copy_hash":
        proof["sha256"] = "0" * 64
    elif mutation == "source_world_readable":
        proof["source_before"]["st_mode"] = 0o100644
    elif mutation == "copy_writable":
        proof["proof_metadata"]["st_mode"] = 0o100644
    elif mutation == "unknown_path":
        proof["source_path"] = "/out/runtime/scoped/private-copy.json"
    else:
        proof["source_before"]["st_nlink"] = True
    data["process/run-1.cli.json"] = contract.canonical(receipt).encode()
    with pytest.raises(ValueError):
        contract.validate_cli(data, 1, before, "fictional-version")


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
@pytest.mark.parametrize("body_failure", [False, True])
def test_cli_export_all_descriptor_closes_preserve_identical_first_fault(
    private_cli_export, monkeypatch, body_failure
):
    output, document, create = private_cli_export
    source, proof = create()
    original = source.read_bytes()
    primary = OSError("original proof write fault")
    close_faults = [OSError("later close one"), OSError("later close two")]
    real_close, real_write = os.close, os.write
    closed, outcomes = [], []

    def close(fd):
        real_close(fd)
        closed.append(fd)
        if len(closed) <= 2:
            raise close_faults[len(closed) - 1]

    def write(fd, data):
        if body_failure:
            raise primary
        return real_write(fd, data)

    monkeypatch.setattr(producer.os, "close", close)
    monkeypatch.setattr(producer.os, "write", write)
    with pytest.raises(OSError) as caught:
        producer.publish_cli_export(1, output, document, cleanup=outcomes)
    assert caught.value is (primary if body_failure else close_faults[0])
    assert len(closed) == len(outcomes) == 4 and len(set(closed)) == 4
    assert [r["failure"]["message"] for r in outcomes if r["failure"]] == [
        "later close one",
        "later close two",
    ]
    assert caught.value.cli_export_close_outcomes == outcomes
    assert source.read_bytes() == original and source.stat().st_mode & 0o777 == 0o600
    assert proof.exists()  # Failed proof is retained; no publication success returned.


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
@pytest.mark.parametrize("body_failure", [False, True])
def test_host_cli_proof_read_retains_primary_and_separate_close_fault(
    tmp_path, monkeypatch, body_failure
):
    proof = tmp_path / "run-1.cli-export.json"
    raw = b'{"original":"retained"}\n'
    proof.write_bytes(raw)
    proof.chmod(0o444)
    real_metadata = contract.export_metadata
    real_close = os.close
    primary, close_fault = (
        ValueError("original proof read fault"),
        OSError("later read close"),
    )
    closed = []

    def metadata(info):
        row = real_metadata(info)
        row["st_uid"] = row["st_gid"] = 0  # Explicit inert UID0 receipt projection.
        return row

    def close(fd):
        real_close(fd)
        closed.append(fd)
        raise close_fault

    class FailedRead:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            raise primary

    monkeypatch.setattr(contract, "export_metadata", metadata)
    monkeypatch.setattr(contract.os, "close", close)
    if body_failure:
        monkeypatch.setattr(contract.os, "fdopen", lambda *a, **k: FailedRead())
    with pytest.raises((ValueError, OSError)) as caught:
        contract.read_export_proof(proof)
    assert caught.value is (primary if body_failure else close_fault)
    assert len(closed) == 1
    assert caught.value.cli_export_close_outcomes == [
        {
            "fd": closed[0],
            "closed": False,
            "failure": {"type": "OSError", "message": "later read close"},
        }
    ]
    assert proof.read_bytes() == raw


@pytest.mark.skipif(os.name != "posix", reason="Linux proof descriptor boundary")
def test_host_cli_proof_actual_copy_read_and_metadata_mismatch_refusal(
    tmp_path, monkeypatch
):
    lifecycle, before, _ = source_cli_exchange(tmp_path, monkeypatch)
    lifecycle.cli_readers(1, before)
    data = final_cli_data(lifecycle)
    original = contract.export_metadata

    def metadata(info):
        row = original(info)
        row["st_uid"] = row["st_gid"] = (
            0  # Structural source fixture, no root-run claim.
        )
        return row

    monkeypatch.setattr(contract, "export_metadata", metadata)
    proof = lifecycle.output / "process/run-1.cli-export.json"
    raw, actual = contract.read_export_proof(proof)
    receipt = contract.json_object(data["process/run-1.cli.json"])
    assert raw == data["process/run-1.cli-export.json"]
    assert actual == receipt["export_proof"]["proof_metadata"]
    # This partial source fixture has no RPC traffic; remove only its known
    # empty fixture directories before exercising the closed inventory reader.
    for name in ("rpc", "inner-rpc"):
        (lifecycle.output / name).rmdir()
    # Exercise profile loading, not only the structural JSON validator.
    (lifecycle.output / "process/run-1.cli.json").write_bytes(
        data["process/run-1.cli.json"]
    )
    contract.profile_artifacts(lifecycle.output)
    receipt["export_proof"]["proof_metadata"]["st_ctime_ns"] += 1
    (lifecycle.output / "process/run-1.cli.json").write_text(
        contract.canonical(receipt)
    )
    with pytest.raises(ValueError, match="Actual CLI proof metadata"):
        contract.profile_artifacts(lifecycle.output)
    proof.chmod(0o644)
    with pytest.raises(ValueError, match="ownership, mode or bound"):
        contract.read_export_proof(proof)


@pytest.mark.parametrize("body_failure", [False, True])
def test_export_descriptor_owner_preserves_false_unprintable_exception_and_closes_all(
    body_failure,
):
    """Pure ownership/error fixture: no filesystem, OS modes or process claim."""

    class CloseFault(BaseException):
        def __bool__(self):
            raise AssertionError("Cleanup must not ask exception truthiness.")

        def __str__(self):
            raise RuntimeError("Rendering cannot prevent another close.")

        @property
        def __dict__(self):
            raise AssertionError("Cleanup must not inspect a subclass dictionary.")

    primary = ValueError("first body error")
    close_fault = CloseFault()
    second_fault = OSError("second close error")
    attempted, outcomes = [], []

    def close(descriptor):
        attempted.append(descriptor)
        if descriptor == 13:
            raise close_fault
        if descriptor == 12:
            raise second_fault

    with pytest.raises((ValueError, CloseFault)) as caught:
        with contract.ExportDescriptors(outcomes) as resources:
            for descriptor in (10, 11, 12, 13):
                resources.callback(close, descriptor)
            if body_failure:
                raise primary
    assert caught.value is (primary if body_failure else close_fault)
    assert attempted == [13, 12, 11, 10]
    assert outcomes == [
        {
            "fd": 13,
            "closed": False,
            "failure": {
                "type": "CloseFault",
                "message": "<exception message unavailable>",
            },
        },
        {
            "fd": 12,
            "closed": False,
            "failure": {"type": "OSError", "message": "second close error"},
        },
        {"fd": 11, "closed": True, "failure": None},
        {"fd": 10, "closed": True, "failure": None},
    ]
    assert (
        BaseException.__dict__["__dict__"].__get__(caught.value)[
            "cli_export_close_outcomes"
        ]
        == outcomes
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "unknown_phase",
        "missing_close",
        "duplicate_fd",
        "bool_fd",
        "failed_close",
        "unknown_field",
        "missing_observation",
    ],
)
def test_final_cli_contract_requires_complete_typed_export_cleanup(
    tmp_path,
    monkeypatch,
    mutation,
):
    lifecycle, before, _ = source_cli_exchange(tmp_path, monkeypatch, projection=True)
    lifecycle.cli_readers(1, before)
    data = final_cli_data(lifecycle)
    receipt = contract.json_object(data["process/run-1.cli.json"])
    contract.validate_cli(data, 1, before, "fictional-version")
    cleanup = receipt["export_cleanup"]
    if mutation == "missing":
        del receipt["export_cleanup"]
    elif mutation == "unknown_phase":
        cleanup["other"] = []
    elif mutation == "missing_close":
        cleanup["publish"].pop()
    elif mutation == "duplicate_fd":
        cleanup["publish"][1]["fd"] = cleanup["publish"][0]["fd"]
    elif mutation == "bool_fd":
        cleanup["fresh"][0]["fd"] = True
    elif mutation == "failed_close":
        cleanup["publish"][0].update(
            closed=False, failure={"type": "OSError", "message": "close refused"}
        )
    elif mutation == "unknown_field":
        cleanup["fresh"][0]["other"] = None
    else:
        del cleanup["fresh"][0]["closed"]
    data["process/run-1.cli.json"] = contract.canonical(receipt).encode()
    with pytest.raises(ValueError):
        contract.validate_cli(data, 1, before, "fictional-version")


@pytest.mark.parametrize(
    "fault",
    [
        "stop",
        "stream",
        "capture",
        "nonzero",
        "bool_exit",
        "forced",
        "group",
        "port",
        "notice",
        "snapshot",
        "missing_forced",
        "missing_group",
        "integer_forced",
        "integer_group",
    ],
)
def test_scoped_cli_export_requires_admitted_stopped_app_before_any_reader(
    tmp_path,
    monkeypatch,
    fault,
):
    """Inert lifecycle: ownership failures cannot publish or replay exports."""
    from tools import native_window_smoke as native
    from tools import rc4_recovery_source as source

    runtime, output = exchange(tmp_path, "scoped")
    paths = {name: output / f"process/run-1.{name}" for name in ("stdout", "stderr")}
    paths["stdout"].write_bytes(b"original stdout\n")
    paths["stderr"].write_bytes(b"bad notice" if fault == "notice" else b"notice")
    events = []
    lifecycle = producer.InstalledLifecycle.__new__(producer.InstalledLifecycle)
    lifecycle.runtime, lifecycle.output, lifecycle.profile = runtime, output, "scoped"
    lifecycle.paths, lifecycle.notice = paths, b"notice"
    lifecycle.rows = [{"run": 1, "pid": 4321, "stop_method": "interface_quit"}]
    lifecycle.process = SimpleNamespace(
        poll=lambda: 7 if fault == "nonzero" else False if fault == "bool_exit" else 0
    )

    class Stream:
        def __init__(self, name):
            self.name = name

        def close(self):
            events.append("close " + self.name)
            if fault == "stream" and self.name == "stdout":
                raise OSError("first stream fault")

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, value):
            assert value == 1

        def connect_ex(self, address):
            return 0 if fault == "port" else 111

    def stop(process, row):
        events.append("stop")
        row.update(
            forced_cleanup=fault == "forced", owned_group_remaining=fault == "group"
        )
        if fault == "missing_forced":
            del row["forced_cleanup"]
        elif fault == "missing_group":
            del row["owned_group_remaining"]
        elif fault == "integer_forced":
            row["forced_cleanup"] = 0
        elif fault == "integer_group":
            row["owned_group_remaining"] = 0
        if fault == "stop":
            raise OSError("first stop fault")

    original_capture = source.capture_stream

    def capture(path):
        events.append("capture " + path.suffix[1:])
        if fault == "capture" and path.suffix == ".stdout":
            raise OSError("first capture fault")
        return original_capture(path)

    def snapshot(path):
        events.append("snapshot")
        if fault == "snapshot":
            raise ValueError("first snapshot fault")
        return {"unchanged": True}

    lifecycle.streams = [Stream(name) for name in ("stdout", "stderr")]
    lifecycle.inner = SimpleNamespace(port=1)
    lifecycle.admission = lambda name: {"unchanged": True}
    lifecycle.cli_readers = lambda *args: events.append("forbidden CLI")
    monkeypatch.setattr(native, "stop_process", stop)
    monkeypatch.setattr(producer.socket, "socket", Probe)
    monkeypatch.setattr(source, "capture_stream", capture)
    monkeypatch.setattr(producer, "fixed_snapshot", snapshot)
    with pytest.raises(ValueError):
        lifecycle.reap(1)
    assert "forbidden CLI" not in events
    assert events[:5] == [
        "stop",
        "close stdout",
        "close stderr",
        "capture stderr",
        "capture stdout",
    ]
    row = producer.read_json(output / "process/run-1.json")
    assert row["stderr"]["sha256"] == contract.sha(paths["stderr"].read_bytes())
    assert paths["stdout"].read_bytes() == b"original stdout\n"
    assert not (output / "process/run-1.cli.json").exists()
    assert not (runtime / "state.json").exists()
