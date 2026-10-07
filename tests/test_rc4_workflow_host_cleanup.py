"""Mocked source regressions; no app, browser, container or installed gate runs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import rc4_installed_workflow as producer


@pytest.fixture
def host_cleanup(tmp_path, monkeypatch):
    from tools import native_window_smoke as native
    from tools import rc4_native_handoff as handoff

    tmp_path = tmp_path.resolve()
    (tmp_path / "out/chrome").mkdir(parents=True)
    (tmp_path / "runtime").mkdir()
    session = producer.captured_session_class()(tmp_path, Path("/inert/chromium"))
    events = []
    state = {"elapsed": 0.0, "alive": {}, "port_errors": {}}
    relay = SimpleNamespace(
        serve_forever=lambda: None,
        server_address=("127.0.0.1", 12345),
        model_requests=0,
        errors=0,
        shutdown=lambda: events.append("relay shutdown"),
        server_close=lambda: events.append("relay close"),
        idle=lambda: events.append("relay idle") or True,
    )
    thread = SimpleNamespace(
        is_alive=lambda: events.append("thread alive") or False,
        join=lambda **kwargs: events.append("relay join"),
    )

    def stop(process, row):
        events.append("chrome reap")
        process.returncode = 0
        row.update(exit_code=0, owned_group_remaining=False)

    def alive(pid):
        events.append(("pid", pid))
        value = state["alive"].get(pid, False)
        if isinstance(value, BaseException):
            raise value
        return value

    def port_closed(port):
        events.append(("port", port))
        if port in state["port_errors"]:
            raise state["port_errors"][port]
        return True

    def sleep(seconds):
        state["elapsed"] += seconds

    monkeypatch.setattr(native, "stop_process", stop)
    monkeypatch.setattr(handoff, "alive", alive)
    monkeypatch.setattr(producer, "closed_port", port_closed)
    monkeypatch.setattr(producer.time, "monotonic", lambda: state["elapsed"])
    monkeypatch.setattr(producer.time, "sleep", sleep)
    observation = {
        "schema": producer.contract.HOST,
        "failure": None,
        "cleanup_errors": [],
        "cleanup_attempts": [],
        "session": {},
        "relay": {},
        "chrome": {},
        "driver": {},
        "browser_pids": [],
        "owned_pids_gone": False,
    }
    proof = SimpleNamespace(
        root=tmp_path,
        session=session,
        relay=relay,
        thread=thread,
        events=events,
        state=state,
        observation=observation,
    )
    yield proof
    for stream in session.chrome_streams.values():
        try:
            stream.close()
        except OSError:
            stream.stream.close()


def acquired(proof):
    """Inject explicit inert ownership rather than launching any resource."""
    session = proof.session

    class Process:
        pid = 7001
        returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, *, timeout):
            proof.events.append("chrome wait")
            self.returncode = 0

    session.chrome_process = Process()
    session.cdp = SimpleNamespace(send=lambda command: proof.events.append(command))
    session.resource_states.update({key: "acquired" for key in session.resource_states})
    for name in ("stdout", "stderr"):
        path = proof.root / "out/chrome" / name
        session.chrome_streams[name] = path.open("xb")
        session.chrome_streams[name].write((name + " inert bytes\n").encode())
    session.chrome_row = {
        "pid": 7001,
        "debug_port": 12346,
        "sigterm_sent": False,
        "forced_cleanup": False,
    }
    session.browser_pids = {7001, 7003}
    session.driver_observation = {
        "pid": 7002,
        "path": "/inert/node",
        "sha256": "a" * 64,
        "cmdline": {},
        "gone": False,
    }
    session.driver_closed = True
    session.browsers = [SimpleNamespace(closed=True)]
    session.contexts = [SimpleNamespace(closed=True)]
    return session


def clean(proof, primary=None, *, started=True):
    attempts = producer.Attempts(primary)
    producer.cleanup_host_resources(
        proof.root,
        proof.session,
        proof.relay,
        proof.thread,
        started,
        proof.observation,
        attempts,
    )
    return attempts


def test_startup_failure_before_browser_keeps_first_without_key_errors(host_cleanup):
    proof = host_cleanup
    first = ValueError("inert installed process failed before browser entry")
    attempts = clean(proof, first)
    assert attempts.first is first and attempts.errors == []
    skipped = [row for row in attempts.rows if row.get("attempted") is False]
    assert len(skipped) == 6
    assert all(row["succeeded"] is False for row in skipped)
    assert {row["state"] for row in skipped} == {"never-created"}
    assert proof.observation["session"]["driver_closed"] is False
    assert proof.observation["session"]["browser_closed"] is False
    assert proof.observation["session"]["contexts_closed"] is False
    assert proof.observation["driver"]["acquisition"] == "never-created"
    assert proof.observation["chrome"]["acquisition"]["process"] == "never-created"
    assert proof.observation["chrome"]["streams_complete"] is False
    assert "gone" not in proof.observation["driver"]
    assert proof.observation["owned_pids_gone"] is False
    assert "relay shutdown" in proof.events and "relay join" in proof.events
    assert producer.read_json(proof.root / "runtime/control.json") == {
        "action": "cleanup"
    }
    with pytest.raises(ValueError) as raised:
        attempts.raise_first()
    assert raised.value is first


def test_host_entry_startup_failure_keeps_original_and_no_prebrowser_key_errors(
    host_cleanup,
    monkeypatch,
):
    """Exercise the real host finally with inert source/setup dependencies."""
    from tools import installed_workflow_browser as browser
    from tools import installed_workflow_qualification as qualification
    from tools import rc4_installed_recovery as recovery

    proof = host_cleanup
    root = proof.root
    (root / "out/chrome").rmdir()
    (root / "candidate").mkdir()
    (root / "candidate/workflow-input.json").write_text("{}", encoding="utf-8")
    (root / "source").mkdir()
    (root / "source/inert.py").write_bytes(b"# inert SOURCE unit fixture\n")
    qa = {"inert.py": {"bytes": 27, "sha256": "a" * 64}}
    inputs = {
        "browser": {"path": "/inert/chromium"},
        "qa_files": qa,
        "package_receipt_name": "inert-package.json",
    }
    first = ValueError("inert installed process failed before browser acquisition")
    report = {"checks": [], "resources": {}}

    def startup(*args):
        raise first

    proof.thread.start = lambda: proof.events.append("relay start")
    monkeypatch.setattr(producer, "ROOT", root / "source")
    monkeypatch.setenv("TMPDIR", str(root / "t"))
    monkeypatch.setattr(producer.contract, "config", lambda value: inputs)
    monkeypatch.setattr(recovery, "source_records", lambda folder: qa)
    monkeypatch.setattr(producer, "wait", lambda path: {"operations_catalog": []})
    monkeypatch.setattr(producer, "receipt", lambda *args: report)
    monkeypatch.setattr(
        qualification, "validate_operations_catalog", lambda *args: None
    )
    monkeypatch.setattr(
        producer, "captured_session_class", lambda: lambda *a: proof.session
    )
    monkeypatch.setattr(browser, "Relay", lambda folder: proof.relay)
    monkeypatch.setattr(browser, "wait_state", startup)
    monkeypatch.setattr(producer.threading, "Thread", lambda **kwargs: proof.thread)
    with pytest.raises(ValueError) as raised:
        producer.host(root, "/inert/chromium")
    assert raised.value is first
    retained = producer.read_json(root / "out/host.json")
    assert retained["failure"] == {"type": "ValueError", "message": str(first)}
    assert retained["cleanup_errors"] == []
    assert retained["session"]["driver_closed"] is False
    assert retained["session"]["browser_closed"] is False
    assert retained["session"]["contexts_closed"] is False
    assert retained["driver"]["acquisition"] == "never-created"
    assert retained["owned_pids_gone"] is False
    assert str(first) in (root / "out/host-failure.txt").read_text(encoding="utf-8")
    assert report["resources"]["installed_process_stopped"] is False
    assert report["resources"]["browser_closed"] is False


def test_process_attempt_without_identity_remains_uncertain(host_cleanup):
    proof = host_cleanup
    proof.session.resource_states["process"] = "uncertain"
    first = OSError("inert Popen failed without returning an owner")
    attempts = clean(proof, first)
    assert attempts.first is first and attempts.errors == []
    assert proof.observation["chrome"]["acquisition"]["process"] == "uncertain"
    assert proof.observation["owned_pids_gone"] is False
    assert "chrome reap" not in proof.events
    assert any(row.get("state") == "uncertain" for row in attempts.rows)


def test_partial_stream_acquisition_only_captures_and_closes_actual_handle(
    host_cleanup,
):
    proof = host_cleanup
    stream = (proof.root / "out/chrome/stdout").open("xb")
    stream.write(b"partial acquisition bytes")
    proof.session.chrome_streams["stdout"] = stream
    proof.session.resource_states.update(stdout="acquired", stderr="uncertain")
    first = OSError("inert stderr open failed")
    attempts = clean(proof, first)
    assert attempts.first is first and attempts.errors == []
    assert stream.closed
    assert proof.observation["chrome"]["stdout"]["bytes"] == 25
    assert "stderr" not in proof.observation["chrome"]
    assert proof.observation["chrome"]["acquisition"]["stderr"] == "uncertain"


@pytest.mark.parametrize("stage", ["stderr", "process"])
def test_actual_chrome_acquisition_flags_survive_stream_or_popen_failure(
    host_cleanup,
    monkeypatch,
    stage,
):
    proof = host_cleanup
    (proof.root / "client").mkdir()
    first = OSError("inert acquisition " + stage + " failure")
    ordinary = Path.open

    def open_stream(path, *args, **kwargs):
        if stage == "stderr" and path == proof.root / "out/chrome/stderr":
            raise first
        return ordinary(path, *args, **kwargs)

    def fail_spawn(*args, **kwargs):
        assert stage == "process"
        raise first

    monkeypatch.setattr(Path, "open", open_stream)
    monkeypatch.setattr(producer.subprocess, "Popen", fail_spawn)
    with pytest.raises(OSError) as raised:
        proof.session.start_chrome(SimpleNamespace())
    assert raised.value is first
    states = proof.session.resource_states
    assert states["stdout"] == "acquired"
    assert states["stderr"] == ("uncertain" if stage == "stderr" else "acquired")
    assert states["process"] == ("never-created" if stage == "stderr" else "uncertain")
    attempts = clean(proof, first)
    assert attempts.first is first and attempts.errors == []
    assert all(stream.closed for stream in proof.session.chrome_streams.values())
    assert proof.observation["chrome"]["streams_complete"] is False


def test_actual_driver_identity_failure_keeps_candidates_without_false_owner(
    host_cleanup,
    monkeypatch,
):
    from tools import rc4_installed_recovery as recovery
    from tools import rc4_native_handoff as handoff

    proof = host_cleanup
    values = iter(({8100}, {8100, 7101, 7102}))
    proof.session.manager = SimpleNamespace(
        __exit__=lambda *args: proof.events.append("driver close"),
    )
    monkeypatch.setattr(handoff, "children", lambda: next(values))
    monkeypatch.setattr(
        recovery.OwnedBrowserSession, "__enter__", lambda self: object()
    )
    with pytest.raises(
        ValueError, match="One actual continuing managed Node"
    ) as raised:
        proof.session.__enter__()
    assert proof.session.resource_states["driver"] == "acquired"
    assert proof.session.driver_observation == {"candidates": [7101, 7102]}
    assert proof.events == ["driver close"]
    attempts = clean(proof, raised.value)
    assert attempts.first is raised.value
    assert proof.observation["driver"]["candidate_observations"] == [
        {"pid": 7101, "alive": False},
        {"pid": 7102, "alive": False},
    ]
    assert "gone" not in proof.observation["driver"]
    assert proof.observation["owned_pids_gone"] is False


def test_owned_process_without_cdp_still_reaps_without_invented_close(host_cleanup):
    proof = host_cleanup
    session = acquired(proof)
    session.cdp = None
    session.chrome_process.returncode = None
    session.resource_states["cdp"] = "uncertain"
    first = OSError("inert CDP acquisition failed")
    attempts = clean(proof, first)
    assert attempts.first is first and attempts.errors == []
    assert attempts.rows[0]["attempted"] is False
    assert attempts.rows[0]["state"] == "uncertain"
    assert "Browser.close" not in proof.events and "chrome reap" in proof.events
    assert session.chrome_process.poll() == 0


def test_capture_after_flush_failure_and_other_handle_close_still_run(host_cleanup):
    proof = host_cleanup
    session = acquired(proof)
    stream = session.chrome_streams["stdout"]
    stream.flush()
    flush_error = OSError("inert flush fault")
    close_error = OSError("inert close fault")

    class FaultStream:
        def __init__(self):
            self.stream = stream

        def flush(self):
            raise flush_error

        def close(self):
            self.stream.close()
            raise close_error

    session.chrome_streams["stdout"] = FaultStream()
    first = ValueError("inert startup primary")
    attempts = clean(proof, first)
    assert attempts.first is first
    assert [row["message"] for row in attempts.errors] == [
        str(flush_error),
        str(close_error),
    ]
    assert session.chrome_row["stdout"]["bytes"] > 0
    assert session.chrome_row["streams_complete"] is False
    assert session.chrome_streams["stderr"].closed
    assert proof.observation["relay"]["port_closed"] is True
    control = producer.read_json(proof.root / "runtime/control.json")
    assert control["action"] == "cleanup"


def test_independent_observations_survive_debugger_and_driver_faults(host_cleanup):
    proof = host_cleanup
    acquired(proof)
    port_error = OSError("inert port fault")
    driver_error = OSError("inert driver fault")
    proof.state["port_errors"][12346] = port_error
    proof.state["alive"][7002] = driver_error
    first = ValueError("inert startup primary")
    attempts = clean(proof, first)
    assert attempts.first is first
    assert {row["message"] for row in attempts.errors} == {
        str(port_error),
        str(driver_error),
    }
    assert proof.observation["relay"] == {
        "stopped": True,
        "idle": True,
        "port_closed": True,
        "model_routes": 0,
        "errors": 0,
    }
    assert ("pid", 7001) in proof.events and ("pid", 7003) in proof.events
    assert proof.observation["driver"]["gone"] is False
    assert proof.observation["chrome"]["debug_port_closed"] is None


def test_ambiguous_driver_candidates_retain_independent_actual_observations(
    host_cleanup,
):
    proof = host_cleanup
    proof.session.resource_states["driver"] = "acquired"
    proof.session.driver_observation = {"candidates": [7101, 7102]}
    proof.state["alive"][7101] = OSError("inert candidate observation fault")
    first = ValueError("inert ambiguous managed driver identity")
    attempts = clean(proof, first)
    driver = proof.observation["driver"]
    assert attempts.first is first and driver["identity_known"] is False
    assert driver["candidate_observations"] == [
        {"pid": 7101, "alive": None},
        {"pid": 7102, "alive": False},
    ]
    assert "gone" not in driver and proof.observation["owned_pids_gone"] is False
    assert proof.observation["relay"]["port_closed"] is True


@pytest.mark.parametrize("survivor", ["thread", "port"])
def test_relay_observation_fault_does_not_hide_an_observed_survivor(
    host_cleanup, monkeypatch, survivor
):
    proof = host_cleanup
    first = ValueError("inert startup primary")
    idle_error = OSError("inert idle observation fault")

    def idle():
        raise idle_error

    proof.thread.is_alive = lambda: survivor == "thread"
    ordinary = producer.closed_port
    monkeypatch.setattr(
        producer,
        "closed_port",
        lambda port: False if survivor == "port" and port == 12345 else ordinary(port),
    )
    proof.relay.idle = idle
    attempts = clean(proof, first)
    assert attempts.first is first
    assert {row["message"] for row in attempts.errors} == {
        str(idle_error),
        "Host relay survives.",
    }
    assert proof.observation["relay"]["stopped"] is (survivor != "thread")
    assert proof.observation["relay"]["port_closed"] is (survivor != "port")
    assert proof.observation["relay"]["model_routes"] == 0
    assert "idle" not in proof.observation["relay"]


def test_acquired_success_keeps_normal_ledger_and_schema(host_cleanup):
    proof = host_cleanup
    acquired(proof)
    attempts = clean(proof)
    assert attempts.first is None and attempts.errors == []
    expected = (
        "browser close request",
        "chrome reap",
        "chrome stdout",
        "chrome stderr",
        "chrome stdout close",
        "chrome stderr close",
        "relay shutdown",
        "relay close",
        "relay join",
        "host resource observation",
        "installed cleanup request",
    )
    assert attempts.rows == [{"resource": name, "succeeded": True} for name in expected]
    assert "acquisition" not in proof.observation["chrome"]
    assert set(proof.observation["driver"]) == {
        "pid",
        "path",
        "sha256",
        "cmdline",
        "gone",
    }
    assert proof.observation["owned_pids_gone"] is True
    assert proof.observation["driver"]["gone"] is True
    assert proof.observation["chrome"]["streams_complete"] is True
    assert proof.observation["session"]["browser_closed"] is True
    assert proof.observation["session"]["contexts_closed"] is True


def test_traceback_retention_fault_keeps_primary_and_attempts_other_retention(
    host_cleanup,
    monkeypatch,
):
    proof = host_cleanup
    first, later = ValueError("inert startup primary"), OSError("inert trace retention")
    attempts = clean(proof, first)
    output = proof.root / "out/workflow"
    output.mkdir()
    report = {"resources": {}}
    ordinary = Path.write_text

    def fault(path, *args, **kwargs):
        if path.name == "host-failure.txt":
            raise later
        return ordinary(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fault)
    producer.retain_host_result(
        proof.root,
        output,
        report,
        proof.observation,
        attempts,
        "inert original traceback",
        completed=False,
    )
    assert attempts.first is first
    assert attempts.errors[-1]["message"] == str(later)
    assert (proof.root / "out/host.json").is_file()
    assert (output / "installed-workflow-browser.pending.json").is_file()
    retained = producer.read_json(proof.root / "out/host.json")
    assert retained["cleanup_errors"][-1]["message"] == str(later)
    assert report["resources"]["installed_process_stopped"] is False


def test_falsey_original_error_is_not_replaced_by_independent_cleanup_failure():
    class FalseyError(ValueError):
        def __bool__(self):
            return False

    first = FalseyError("inert original falsey error")
    later = OSError("inert later cleanup failure")
    attempts = producer.Attempts(first)

    def fail():
        raise later

    attempts.independent("inert observation group", (("inert observer", fail),))
    attempts.call("inert later operation", fail)
    assert attempts.first is first
    assert len(attempts.errors) == 2
    with pytest.raises(FalseyError) as raised:
        attempts.raise_first()
    assert raised.value is first


@pytest.mark.parametrize(
    "failed_names",
    [
        ("host.json",),
        ("installed-workflow-browser.pending.json",),
        ("host.json", "installed-workflow-browser.pending.json"),
    ],
)
def test_each_retention_fault_keeps_original_and_attempts_other_outputs(
    host_cleanup, monkeypatch, capsys, failed_names
):
    proof = host_cleanup
    first = ValueError("inert startup primary")
    attempts = clean(proof, first)
    output = proof.root / "out/workflow"
    output.mkdir()
    report = {"resources": {}}
    writes = []
    ordinary = producer.write_json

    def fault(path, value):
        writes.append(path.name)
        if path.name in failed_names:
            raise OSError("inert retention fault: " + path.name)
        ordinary(path, value)

    monkeypatch.setattr(producer, "write_json", fault)
    producer.retain_host_result(
        proof.root,
        output,
        report,
        proof.observation,
        attempts,
        "inert original traceback",
        completed=False,
    )
    assert writes == ["host.json", "installed-workflow-browser.pending.json"]
    assert attempts.first is first
    assert [row["message"] for row in attempts.errors] == [
        "inert retention fault: " + name for name in failed_names
    ]
    assert (proof.root / "out/host-failure.txt").read_text(
        encoding="utf-8"
    ) == "inert original traceback"
    with pytest.raises(ValueError) as raised:
        attempts.raise_first()
    assert raised.value is first
    retained_stderr = capsys.readouterr().err
    assert all(name in retained_stderr for name in failed_names)
    assert report["resources"]["browser_closed"] is False
    assert report["resources"]["installed_process_stopped"] is False
