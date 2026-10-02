"""Finite source/IPC/ownership controls only; no installer or installed pass fixture."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from tools import rc4_installed_recovery as producer
from tools import rc4_installed_recovery_contract as contract


def removal_observation():
    """An ordinary reaped child exercises ownership, never an installed package."""
    from tools import installed_native_menu as menu

    rows = []
    menu.command([sys.executable, "-I", "-S", "-B", "-c", "pass"], rows)
    row = rows[-1]
    row["argv"] = ["dpkg", "-r", "sinter"]
    return row, {"package_state": "absent", "remaining_paths": [], "passed": True}


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
    from tools import installed_native_menu as menu

    progress = b"Removing sinter (fictional ordinary child observation) ...\n"
    rows = []
    menu.command(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import os;os.write(1,"
            + repr(progress)
            + ");os.write(2,"
            + repr(contract.REMOVAL_NOTICE)
            + ")",
        ],
        rows,
    )
    # Only the record's argv is projected; this never executes dpkg or installs.
    row = rows[-1]
    row["argv"] = ["dpkg", "-r", "sinter"]
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
        json.loads((output / "process/run-1.before-reader.json").read_text()) == before
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
    actual = menu.command
    called = []

    def failed(argv, rows, **kw):
        called.append(list(map(str, argv)))
        actual(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                "import os;os.write(2,b'\\xff owned CLI diagnostic\\n')",
            ],
            rows,
            **kw,
        )
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
    actual = menu.command
    called = []

    def changed(argv, rows, **kw):
        called.append(list(map(str, argv)))
        result = actual(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                'print(\'{"ok":true,"version":"fictional-version"}\')',
            ],
            rows,
            **kw,
        )
        with sqlite3.connect(lifecycle.runtime / "data/workspace.sqlite3") as db:
            db.execute("PRAGMA application_id=987")
        return result

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
    from tools import installed_native_menu as menu

    rows = []
    menu.command(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import os;os.write(2," + repr(diagnostic) + ")",
        ],
        rows,
    )
    # Ordinary finite child bytes exercise the diagnostic predicate only, not dpkg.
    rows[-1]["argv"] = ["dpkg", "-r", "sinter"]
    state = {"package_state": "absent", "remaining_paths": [], "passed": True}
    if diagnostic in (b"", contract.REMOVAL_NOTICE):
        contract.validate_package_removal(0, rows[-1], state, rows)
    else:
        with pytest.raises(ValueError, match="Unexpected package"):
            contract.validate_package_removal(0, rows[-1], state, rows)


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


def test_actual_unix_partial_request_worker_is_closed_before_ownership_pass(tmp_path):
    import socket

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
