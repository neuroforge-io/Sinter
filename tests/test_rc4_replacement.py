"""Source/seam controls; no test builds, installs or qualifies a real package."""

from __future__ import annotations

import base64
import copy
import io
import json
import socket
import stat
import sys
import threading
import time
from pathlib import Path, PurePosixPath
from types import ModuleType, SimpleNamespace

import pytest

from tools import rc4_replacement as producer
from tools import rc4_replacement_contract as contract
from tools import rc4_replacement_probe as probe


def saved_workspace(tmp_path):
    from sinter.campaigns import CampaignStore
    from sinter.casebooks import Casebooks
    from sinter.preferences import Preferences
    from sinter.store import Store

    store = Store(tmp_path)
    Preferences(tmp_path).update(
        {"model": "fictional-explicit-model", "theme": "light"}
    )
    Casebooks(store).save(
        {
            "title": "Fictional original",
            "questions": "Permission?",
            "documents": [{"title": "Original", "content": "Unknown e\u0301 🐝"}],
        }
    )
    report = {
        "title": "Historical report",
        "markdown": "Unknown e\u0301 🐝",
        "document_edits": {"markdown": "Literal human words e\u0301 🐝"},
    }
    store.save_report(report)
    store.add_watch("Disabled fictional watch", "fictional", 86400)
    with store.connect() as db:
        db.execute("UPDATE watches SET enabled=0")
    CampaignStore(tmp_path).save(
        {"title": "Fictional campaign", "requirements": [], "actions": []}
    )
    return contract.snapshot(tmp_path)


def test_new_prior_route_never_mutates_historical_admission():
    from tools.qualified_priors import QUALIFIED_PRIORS, qualified_prior
    from tools.upgrade_smoke import prior_for_arguments

    assert tuple(contract.PRIORS) == ("0.5.3", "0.5.4rc1", "0.5.4rc2", "0.5.4rc3")
    assert tuple(QUALIFIED_PRIORS) == ("0.5.3", "0.5.4rc1", "0.5.4rc2")
    for prior in contract.PRIORS.values():
        assert contract.select_prior(prior.version, prior.source_commit) == prior
        with pytest.raises(ValueError):
            prior_for_arguments(
                SimpleNamespace(
                    prior_version=prior.version,
                    prior_commit=prior.source_commit,
                    expected_version=contract.VERSION,
                )
            )
    with pytest.raises(ValueError):
        qualified_prior(
            contract.PUBLISHED_E.version, contract.PUBLISHED_E.source_commit
        )
    with pytest.raises(TypeError):
        contract.PRIORS["0.5.4rc3"] = None


@pytest.mark.parametrize("value", [None, True, 4, [], {}, "0.5.4rc4.dev0", "0.5.5"])
def test_only_final_target_and_exact_prior_types(value):
    prior = contract.PUBLISHED_E
    with pytest.raises(ValueError):
        contract.select_prior(prior.version, prior.source_commit, value)
    with pytest.raises(ValueError):
        contract.select_prior(value, prior.source_commit)
    with pytest.raises(ValueError):
        contract.select_prior(prior.version, value)


def test_full_original_preferences_rows_and_literal_history(tmp_path):
    original = saved_workspace(tmp_path)
    contract.preserve(original, copy.deepcopy(original), original["databases"])
    assert b"e\xcc\x81" in contract.raw_blob(
        original["preferences_original"]
    ) or "e\u0301" in contract.encoded(original["databases"])
    assert "Literal human words e\u0301 🐝" in contract.encoded(original)


@pytest.mark.parametrize(
    "change",
    [
        "preference",
        "preference-original",
        "boolean",
        "row",
        "history",
        "metadata",
        "sql",
        "columns",
        "missing-table",
        "extra-table",
    ],
)
def test_complete_conservation_refuses_loss_or_schema_forgery(tmp_path, change):
    original = saved_workspace(tmp_path)
    altered = copy.deepcopy(original)
    workspace = altered["databases"]["workspace.sqlite3"]
    if change == "preference":
        altered["preferences"]["model"] = "inferred-model"
    elif change == "preference-original":
        altered["preferences_original"] = contract.blob(b"{}")
    elif change == "boolean":
        altered["preferences"]["reduce_motion"] = 0
    elif change == "row":
        workspace["tables"]["casebooks"]["rows"].clear()
    elif change == "history":
        workspace["tables"]["reports"]["rows"][0][-1] = "{}"
    elif change == "metadata":
        workspace["metadata"]["user_version"] += 1
    elif change == "sql":
        workspace["tables"]["casebooks"]["sql"] += " "
    elif change == "columns":
        workspace["tables"]["casebooks"]["columns"].reverse()
    elif change == "missing-table":
        del workspace["tables"]["reports"]
    else:
        workspace["tables"]["foreign"] = {
            "sql": "CREATE TABLE foreign(a)",
            "columns": ["a"],
            "rows": [],
        }
    with pytest.raises(ValueError):
        contract.preserve(original, altered, original["databases"])


def test_only_exact_source_derived_empty_table_addition(tmp_path):
    original = saved_workspace(tmp_path)
    empty = copy.deepcopy(original["databases"])
    row = {"sql": "CREATE TABLE fictional_new(a TEXT)", "columns": ["a"], "rows": []}
    empty["workspace.sqlite3"]["tables"]["fictional_new"] = row
    altered = copy.deepcopy(original)
    altered["databases"]["workspace.sqlite3"]["tables"]["fictional_new"] = (
        copy.deepcopy(row)
    )
    contract.preserve(original, altered, empty)
    altered["databases"]["workspace.sqlite3"]["tables"]["fictional_new"]["rows"] = [
        ["lost original"]
    ]
    with pytest.raises(ValueError):
        contract.preserve(original, altered, empty)


@pytest.mark.parametrize("value", [True, -1, "0", None])
def test_original_byte_counts_are_closed_integer_types(value):
    row = contract.blob(b"original")
    row["bytes"] = value
    with pytest.raises(ValueError):
        contract.raw_blob(row)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_duplicate_or_nonfinite_original_json_refuses(raw):
    with pytest.raises(ValueError):
        contract.json_value(raw)


def normal_process(version="0.5.4rc3"):
    argv = probe.browser_launch_command(["/opt/neuroforge/sinter/Sinter"], version)
    row = {
        "argv": argv,
        "workspace": "/out/run/fixture/copied-for-eventual-replacement",
        "binary_sha256": "a" * 64,
        "pid": 1234,
        "exit_code": 0,
        "reaped": True,
        "forced_cleanup": False,
        "group_remaining": False,
        "listener_closed": True,
        "stdout": contract.blob(b"Sinter local workspace: http://127.0.0.1:4567\n"),
        "stderr": contract.blob(
            b"Press Ctrl+C to stop. Closing a browser tab alone does not quit Sinter.\n"
        ),
    }
    return row, argv


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", True),
        ("exit_code", False),
        ("exit_code", 1),
        ("reaped", 1),
        ("forced_cleanup", True),
        ("group_remaining", True),
        ("listener_closed", False),
        ("workspace", "/another-workspace"),
        ("binary_sha256", "b" * 64),
        ("argv", ["python", "source.py"]),
    ],
)
def test_process_identity_and_normal_owned_stop_are_mandatory(field, value):
    row, argv = normal_process()
    contract.stopped(row, argv, row["workspace"], "a" * 64, "0.5.4rc3")
    row[field] = value
    with pytest.raises(ValueError):
        contract.stopped(
            row,
            argv,
            "/out/run/fixture/copied-for-eventual-replacement",
            "a" * 64,
            "0.5.4rc3",
        )


def test_complete_stream_append_cannot_hide_after_prefix():
    row, argv = normal_process()
    row["stderr"] = contract.blob(
        contract.raw_blob(row["stderr"]) + b"late actual error\n"
    )
    with pytest.raises(ValueError):
        contract.stopped(row, argv, row["workspace"], "a" * 64, "0.5.4rc3")


def package_rows():
    rows = []
    status = producer.STATUS
    prior = "/prior/Sinter-0.5.4rc3-linux-x64.deb"
    candidate = "/candidate/Sinter-0.5.4rc4-linux-x64.deb"
    argv = [
        status,
        ["dpkg", "-i", prior],
        status,
        status,
        ["dpkg", "-i", candidate],
        status,
        status,
        status,
        ["dpkg", "-r", "sinter"],
        status,
    ]
    for index, (role, command) in enumerate(zip(contract.PACKAGE_ROLES, argv)):
        absent = index in {0, 9}
        body = b"" if absent else b"actual install/removal stream\n"
        if index in {2, 3, 5, 6, 7}:
            version = "0.5.4~rc3" if index < 4 else "0.5.4~rc4"
            body = ("install ok installed\n" + version + "\n").encode()
        rows.append(
            {
                "role": role,
                "argv": command,
                "pid": 1000 + index,
                "exit_code": 1 if absent else 0,
                "reaped": True,
                "stdout": contract.blob(body),
                "stderr": contract.blob(
                    b"dpkg-query: no packages found matching sinter\n"
                    if absent
                    else b""
                ),
            }
        )
    return rows, prior, candidate


def command_files(rows, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for row in rows:
        for channel in ("stdout", "stderr"):
            (folder / (row["role"] + "." + channel)).write_bytes(
                contract.raw_blob(row[channel])
            )
    return folder


@pytest.mark.parametrize(
    "change",
    [
        "uninstall-first",
        "wrong-status",
        "wrong-version",
        "boolean-exit",
        "missing-reap",
        "incomplete",
        "arbitrary-absence",
        "late-stderr",
    ],
)
def test_actual_package_status_order_and_complete_post_reap_streams(change, tmp_path):
    rows, prior, candidate = package_rows()
    folder = command_files(rows, tmp_path / "commands")
    contract.package_commands(rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder)
    if change == "uninstall-first":
        rows[4]["argv"] = ["dpkg", "-r", "sinter"]
    elif change == "wrong-status":
        rows[3]["stdout"] = contract.blob(b"deinstall ok config-files\n0.5.4~rc3\n")
    elif change == "wrong-version":
        rows[7]["stdout"] = contract.blob(b"install ok installed\n0.5.4~rc3\n")
    elif change == "boolean-exit":
        rows[5]["exit_code"] = False
    elif change == "missing-reap":
        rows[8]["reaped"] = False
    elif change == "incomplete":
        rows.pop()
    elif change == "arbitrary-absence":
        rows[9]["stderr"] = contract.blob(b"dpkg-query failed unexpectedly\n")
    else:
        rows[8]["stderr"] = contract.blob(b"removal failure after reply\n")
    command_files(rows, folder)
    with pytest.raises(ValueError):
        contract.package_commands(
            rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder
        )


def test_command_retains_original_failure_and_stderr_after_reap(tmp_path):
    rows = []
    row = producer.command(
        [
            sys.executable,
            "-c",
            "import sys;sys.stdout.buffer.write(b'original\\n');"
            "sys.stderr.buffer.write(b'late error\\n');"
            "raise SystemExit(3)",
        ],
        rows,
        "failure",
        tmp_path,
    )
    assert row["exit_code"] == 3 and row["reaped"] is True and row["pid"] > 1
    assert contract.raw_blob(row["stdout"]) == b"original\n"
    assert contract.raw_blob(row["stderr"]) == b"late error\n"
    assert row is rows[0]


def test_shared_five_mount_policy_and_closed_outer_argv(tmp_path):
    shared, _owner = contract.shared()
    pins = {
        key: "/fictional/replacement/" + key
        for key, _destination, _writable in contract.MOUNTS
    }
    pins.update(
        image_id="sha256:" + "a" * 64, source_commit="b" * 40, prior_version="0.5.4rc3"
    )
    mounts = shared.private_mounts(pins, contract.MOUNTS)
    assert len(mounts) == 5 and [row["RW"] for row in mounts].count(True) == 1
    argv = contract.outer_argv(pins, "sinter-native-entry-123456abcdef")
    assert "--pull=never" in argv and argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index(pins["image_id"]) + 1 :] == [
        "python3",
        "-B",
        "/source/tools/rc4_replacement.py",
        "inner",
        "--repository",
        "/repository",
        "--source-route",
        "archive",
        "--source-commit",
        "b" * 40,
        "--prior-version",
        "0.5.4rc3",
        "--candidate",
        "/candidate",
        "--output",
        "/out/run",
    ]
    for value in (
        pins["prior_directory"],
        str(PurePosixPath(pins["source_directory"]).parent),
    ):
        altered = {**pins, "output_directory": value}
        with pytest.raises(ValueError):
            shared.private_mounts(altered, contract.MOUNTS)


def test_fixture_source_seed_environment_excludes_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-never-forwarded")
    monkeypatch.setenv("NEUROFORGE_MODEL", "fictional-never-forwarded")
    environment = producer.seed_environment(tmp_path)
    assert "OPENAI_API_KEY" not in environment and "NEUROFORGE_MODEL" not in environment


def test_private_root_refuses_main_or_ancestor_alias(tmp_path):
    args = SimpleNamespace(
        owned_root=tmp_path,
        repository=tmp_path / "repository",
        candidate=tmp_path / "candidate",
        priors=tmp_path / "priors",
        output=tmp_path / "output",
    )
    contract.private_paths(args, tmp_path / "source")
    with pytest.raises(ValueError):
        contract.private_paths(args, tmp_path.parent / "main")


def test_old_source_or_dev_receipt_is_not_an_installed_replacement(tmp_path):
    for schema in (
        "sinter-published-rc3-fixture/v1",
        "sinter-native-installer-upgrade/v1",
        "sinter-rc4-local-recovery-source/v1",
        "sinter-installed-native-entry-test/v2",
    ):
        with pytest.raises(ValueError):
            contract.validate_inner(
                {"schema": schema, "passed": True}, tmp_path, {}, {}, {}, {}
            )


def mapped_bridge(tmp_path, monkeypatch):
    """Closed mapped seam; this helper never claims an actual installed PID."""
    folder = tmp_path / "profile/run/prior"
    folder.mkdir(parents=True)
    runtime = tmp_path / "profile/bridge/prior"
    runtime.mkdir(parents=True)
    expected = {"prior_version": "0.5.4rc3"}
    producer.write(runtime / "expected.json", expected)
    workspace = "/out/run/fixture/copied-for-eventual-replacement"
    process = {"pid": 1234, "binary_sha256": "a" * 64}
    request = {
        "schema": "sinter-rc4-replacement-bridge/v1",
        "phase": "prior",
        "version": "0.5.4rc3",
        "pid": process["pid"],
        "port": 12345,
        "workspace": str(workspace),
        "binary_sha256": process["binary_sha256"],
        "expected_sha256": contract.sha(contract.regular(runtime / "expected.json")),
        "collector_source_sha256": contract.sha(contract.regular(Path(probe.__file__))),
    }
    producer.write(runtime / "state.json", request)
    (folder / "opened-url.txt").write_text("http://127.0.0.1:12345/", encoding="utf-8")
    response = {
        "request": request,
        "ui": {
            "screenshots": [],
            "resources": {
                "context_pages_after_close": 0,
                "browser_connected_after_close": False,
            },
        },
        "failure": None,
        "resources": {
            "host_port": 23456,
            "host_connect_errno": 111,
            "thread_alive": False,
            "connections_remaining": False,
            "relay_errors": 0,
            "model_route_requests": 0,
            "workers_remaining": 0,
            "sockets_remaining": 0,
            "browser_temp_remaining": [],
        },
    }
    producer.write(runtime / "response.json", response)
    bridge = {
        "request": request,
        "response": response,
        "failure": None,
        "inner_thread_alive": False,
        "inner_socket_remaining": False,
        "inner_workers_remaining": 0,
        "inner_connections_remaining": 0,
    }
    for path, observed in (
        (runtime / "host-diagnostics.json", response["resources"]),
        (runtime / "ui-diagnostics.json", response["ui"]["resources"]),
        (folder / "inner-diagnostics.json", bridge),
    ):
        producer.write(
            path, {"failure": None, "cleanup_failures": [], "resources": observed}
        )
    monkeypatch.setattr(probe, "closed_port", lambda port: 111)
    return bridge, process, expected, workspace, folder, runtime


def test_mapped_closed_bridge_has_explicit_phase_and_actual_sidecars(
    tmp_path, monkeypatch
):
    bridge, process, expected, workspace, folder, _runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    assert contract.validate_bridge(
        bridge, process, expected, "prior", workspace, folder
    ) == {
        "screenshots": [],
        "resources": {
            "context_pages_after_close": 0,
            "browser_connected_after_close": False,
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "sinter-native-entry/v2"),
        ("phase", "candidate"),
        ("version", "0.5.4rc4.dev0"),
        ("pid", True),
        ("pid", 4321),
        ("port", True),
        ("port", 99999),
        ("port", 12346),
        ("workspace", "/out/other"),
        ("workspace", "relative"),
        ("binary_sha256", "b" * 64),
        ("expected_sha256", "b" * 64),
        ("collector_source_sha256", "b" * 64),
        ("extra", "unknown"),
    ],
)
def test_bridge_refuses_swapped_untyped_or_unbound_request(
    tmp_path, monkeypatch, field, value
):
    bridge, process, expected, workspace, folder, runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    bridge["request"][field] = value
    producer.write(runtime / "state.json", bridge["request"])
    producer.write(runtime / "response.json", bridge["response"])
    with pytest.raises(ValueError):
        contract.validate_bridge(bridge, process, expected, "prior", workspace, folder)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host_port", True),
        ("host_connect_errno", False),
        ("host_connect_errno", 0),
        ("thread_alive", 0),
        ("thread_alive", True),
        ("connections_remaining", True),
        ("relay_errors", False),
        ("relay_errors", 1),
        ("model_route_requests", True),
        ("model_route_requests", 1),
        ("workers_remaining", False),
        ("workers_remaining", 1),
        ("sockets_remaining", False),
        ("sockets_remaining", 1),
        ("browser_temp_remaining", ["left-behind"]),
        ("extra", None),
    ],
)
def test_bridge_refuses_live_resources_and_boolean_integer_shortcuts(
    tmp_path, monkeypatch, field, value
):
    bridge, process, expected, workspace, folder, runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    bridge["response"]["resources"][field] = value
    producer.write(runtime / "response.json", bridge["response"])
    with pytest.raises(ValueError):
        contract.validate_bridge(bridge, process, expected, "prior", workspace, folder)


@pytest.mark.parametrize(
    "field,value",
    [
        ("inner_thread_alive", True),
        ("inner_thread_alive", 0),
        ("inner_socket_remaining", True),
        ("inner_workers_remaining", False),
        ("inner_workers_remaining", 1),
        ("inner_connections_remaining", False),
        ("inner_connections_remaining", 1),
        ("failure", "primary failure"),
    ],
)
def test_bridge_refuses_inner_resource_or_primary_failure(
    tmp_path, monkeypatch, field, value
):
    bridge, process, expected, workspace, folder, _runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    bridge[field] = value
    with pytest.raises(ValueError):
        contract.validate_bridge(bridge, process, expected, "prior", workspace, folder)


def test_actual_host_relay_closes_idle_preconnect_workers_and_listener(tmp_path):
    relay = probe.HostRelay(tmp_path)
    server = threading.Thread(target=relay.serve_forever)
    server.start()
    client = socket.create_connection(relay.server_address, timeout=1)
    try:
        deadline = time.monotonic() + 1
        while relay.idle() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not relay.idle()
        port = relay.server_address[1]
        relay.shutdown()
        server.join(timeout=1)
        assert relay.close_owned() == (0, 0)
        assert not server.is_alive() and relay.idle()
        assert probe.closed_port(port) != 0
    finally:
        client.close()
        if server.is_alive():
            relay.shutdown()
            server.join(timeout=1)
        relay.close_owned()


def test_host_collector_replayed_response_refuses_before_browser(tmp_path, monkeypatch):
    bridge, _process, _expected, _workspace, _folder, runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    (runtime / "relay.sock").write_bytes(b"not a socket")
    calls = []
    monkeypatch.setattr(probe, "ui", lambda *args: calls.append(args))
    monkeypatch.setattr(Path, "is_socket", lambda path: path == runtime / "relay.sock")
    with pytest.raises(ValueError):
        probe.collect(runtime, Path("/private/chromium"), "prior", tmp_path / "t")
    assert calls == [] and bridge["response"]["failure"] is None


def test_utf8_atomic_messages_retain_literal_combining_unicode(tmp_path):
    path = tmp_path / "message.json"
    producer.write(path, {"literal": "e\u0301 🐝", "confirmed": False})
    raw = path.read_bytes()
    assert b"e\xcc\x81" in raw and b"\\u0301" not in raw and raw.endswith(b"\n")
    assert json.loads(raw) == {"literal": "e\u0301 🐝", "confirmed": False}
    assert not (tmp_path / "message.json.temporary").exists()


def replacement_lifecycle(tmp_path):
    from test_installed_native_entry_contract import outer_fixture, output, stream

    from tools import installed_native_entry_contract as shared

    bundle, pins = outer_fixture()
    pins.update(
        prior_directory="/home/lloyd/fictional-owner/prior", prior_version="0.5.4rc3"
    )
    creation = contract.outer_argv(pins, "sinter-native-entry-abcdefghijkl")
    bundle["commands"][1]["argv"] = creation
    for index in (2, 4):
        raw = shared.stream_bytes(bundle["commands"][index]["stdout"])
        observed = json.loads(raw)[0]
        observed["Args"] = creation[creation.index(pins["image_id"]) + 2 :]
        observed["Config"]["Cmd"] = creation[creation.index(pins["image_id"]) + 1 :]
        observed["Mounts"] = shared.private_mounts(pins, contract.MOUNTS)
        bundle["commands"][index]["stdout"] = stream(output([observed]))
    return bundle["commands"], pins


def test_shared_raw_seven_roles_use_actual_replacement_argv_and_five_mounts(tmp_path):
    from tools import installed_native_entry_contract as shared

    rows, pins = replacement_lifecycle(tmp_path)
    assert (
        shared.validate_lifecycle(rows, pins, contract.outer_argv, contract.MOUNTS)[
            "container_id"
        ]
        == "2" * 64
    )
    with pytest.raises(ValueError):
        shared.validate_lifecycle(rows, pins, shared.outer_argv)


@pytest.mark.parametrize(
    "attack",
    [
        "extra-mount",
        "prior-rw",
        "prior-alias",
        "command",
        "image",
        "bad-finish",
        "bool-pid",
        "bool-exit",
        "running",
        "oom",
        "error",
    ],
)
def test_replacement_reuses_shared_raw_ownership_and_lifecycle_refusals(
    tmp_path, attack
):
    from test_installed_native_entry_contract import output, stream

    from tools import installed_native_entry_contract as shared

    rows, pins = replacement_lifecycle(tmp_path)
    if attack == "prior-alias":
        pins["prior_directory"] = pins["output_directory"] + "/nested"
    elif attack == "command":
        rows[1]["argv"][-1] = "/different"
    else:
        observed = json.loads(shared.stream_bytes(rows[4]["stdout"]))[0]
        if attack == "extra-mount":
            observed["Mounts"].append(
                {
                    "Type": "bind",
                    "Source": "/unowned",
                    "Destination": "/extra",
                    "RW": False,
                }
            )
        elif attack == "prior-rw":
            next(row for row in observed["Mounts"] if row["Destination"] == "/prior")[
                "RW"
            ] = True
        elif attack == "image":
            observed["Image"] = "sha256:" + "1" * 64
        else:
            key, value = {
                "bad-finish": ("FinishedAt", "unproved"),
                "bool-pid": ("Pid", False),
                "bool-exit": ("ExitCode", False),
                "running": ("Running", True),
                "oom": ("OOMKilled", True),
                "error": ("Error", "actual failure"),
            }[attack]
            observed["State"][key] = value
        rows[4]["stdout"] = stream(output([observed]))
    with pytest.raises(ValueError):
        shared.validate_lifecycle(rows, pins, contract.outer_argv, contract.MOUNTS)


def test_complete_outer_stream_sidecars_reject_hidden_append_or_boolean_pid(tmp_path):
    from tools import installed_native_entry_contract as shared

    rows, _pins = replacement_lifecycle(tmp_path)
    streams = tmp_path / "outer-streams"
    streams.mkdir()
    for index, row in enumerate(rows):
        actual = {key: row[key] for key in ("role", "argv", "exit_code", "reaped")}
        actual["pid"] = 1000 + index
        for channel in ("stdout", "stderr"):
            raw = shared.stream_bytes(row[channel])
            actual[channel] = contract.blob(raw)
            (streams / (row["role"] + "." + channel)).write_bytes(raw)
        producer.write(tmp_path / (row["role"] + "-command.json"), actual)
    contract.outer_sidecars(rows, tmp_path)
    (streams / "start.stderr").write_bytes(b"late failure after recorded prefix")
    with pytest.raises(ValueError):
        contract.outer_sidecars(rows, tmp_path)
    (streams / "start.stderr").write_bytes(b"")
    actual = json.loads((tmp_path / "start-command.json").read_text())
    actual["pid"] = True
    producer.write(tmp_path / "start-command.json", actual)
    with pytest.raises(ValueError):
        contract.outer_sidecars(rows, tmp_path)


@pytest.mark.parametrize("collector_failure", [False, True])
def test_mapped_attach_and_collector_lost_reply_never_replays(
    tmp_path, monkeypatch, collector_failure
):
    calls, attach_calls, records = [], [], []
    for phase in contract.RUN_ORDER:
        (tmp_path / "bridge" / phase).mkdir(parents=True)

    def start():
        attach_calls.append("once")
        for phase in contract.RUN_ORDER:
            runtime = tmp_path / "bridge" / phase
            producer.write(runtime / "state.json", {"mapped_phase": phase})
            deadline = time.monotonic() + 2
            while (
                not (runtime / "response.json").exists() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert (runtime / "response.json").exists()
            if json.loads((runtime / "response.json").read_text())["failure"]:
                raise ValueError(
                    "Mapped inner primary failure; not a product observation"
                )
        return {
            "exit_code": 1,
            "reaped": True,
            "stdout": contract.blob(b"lost attach reply"),
        }

    def collector(argv, rows, role, directory, timeout, owned_group):
        calls.append(role)
        failure = collector_failure and role == contract.RUN_ORDER[1]
        producer.write(
            tmp_path / "bridge" / role / "response.json", {"failure": failure}
        )
        row = {
            "role": role,
            "argv": argv,
            "pid": 222 + len(calls),
            "exit_code": int(failure),
            "reaped": True,
            "forced_cleanup": False,
            "group_remaining": False,
            "stdout": contract.blob(b"mapped"),
            "stderr": contract.blob(b"primary" if failure else b""),
        }
        rows.append(row)
        return row

    monkeypatch.setattr(producer, "command", collector)
    if collector_failure:
        with pytest.raises(ValueError, match="Host collector failed"):
            producer.start_with_collectors(
                start, tmp_path, Path("/private/chromium"), records, tmp_path / "t"
            )
        assert calls == list(contract.RUN_ORDER[:2])
    else:
        result = producer.start_with_collectors(
            start, tmp_path, Path("/private/chromium"), records, tmp_path / "t"
        )
        assert result["exit_code"] == 1 and calls == list(contract.RUN_ORDER)
    assert attach_calls == ["once"]


@pytest.mark.parametrize(
    "attack",
    [
        "unknown-mode",
        "source-loss",
        "broad-source",
        "empty-becomes-selected",
        "boolean-index",
        "fingerprint",
        "extra-top",
    ],
)
def test_closed_v2_reader_preserves_exact_explicit_scope_semantics(attack):
    original = {
        "id": "fictional",
        "revision": 2,
        "document": {
            "schema": "sinter-casebook/v2",
            "title": "Fictional closed scope",
            "question_scopes": [
                {"question_index": 0, "source_ids": ["Sone"]},
                {"question_index": 1, "source_ids": []},
            ],
            "fingerprint": "original",
        },
    }
    contract.book_view(original, copy.deepcopy(original))
    current = copy.deepcopy(original)
    scope = current["document"]["question_scopes"]
    if attack == "unknown-mode":
        scope[0]["mode"] = "all"
    elif attack == "source-loss":
        scope[0]["source_ids"] = []
    elif attack == "broad-source":
        scope[0]["source_ids"].append("Stwo")
    elif attack == "empty-becomes-selected":
        scope[1]["source_ids"] = ["Sone"]
    elif attack == "boolean-index":
        scope[0]["question_index"] = False
    elif attack == "fingerprint":
        current["document"]["fingerprint"] = "invented"
    else:
        current["document"]["unreviewed_scope"] = "all"
    with pytest.raises(ValueError):
        contract.book_view(original, current)


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", False),
        ("exit_code", 1),
        ("pid", True),
        ("pid", 0),
        ("reaped", False),
        ("stdout", b"--force\n"),
        ("stdout", b"a" * 63 + b"\n"),
        ("stdout", b"A" * 64 + b"\n"),
        ("stdout", b"a" * 64),
        ("stdout", b" " + b"a" * 64 + b"\n"),
        ("stdout", b"a" * 64 + b"\n" + b"b" * 64 + b"\n"),
    ],
)
def test_failed_or_malformed_create_cannot_authorize_cleanup_id(field, value):
    row = {
        "exit_code": 0,
        "pid": 100,
        "reaped": True,
        "stdout": contract.blob(b"a" * 64 + b"\n"),
        "stderr": contract.blob(b""),
    }
    assert producer.created_identifier(row) == "a" * 64
    row[field] = contract.blob(value) if field == "stdout" else value
    with pytest.raises(ValueError):
        producer.created_identifier(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", False),
        ("exit_code", 1),
        ("pid", True),
        ("reaped", False),
        ("stderr", b"actual error"),
        ("stdout", b"[]"),
        ("stdout", b"{}"),
        ("stdout", b"[{},{}]"),
        ("stdout", b"[false]"),
    ],
)
def test_bad_actual_inspection_cannot_start_installed_work(field, value):
    row = {
        "exit_code": 0,
        "pid": 100,
        "reaped": True,
        "stdout": contract.blob(b"[{}]"),
        "stderr": contract.blob(b""),
    }
    assert producer.inspected_json(row) == {}
    row[field] = contract.blob(value) if field in {"stdout", "stderr"} else value
    with pytest.raises(ValueError):
        producer.inspected_json(row)


@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("attack", ["combining", "emoji", "title"])
def test_saved_report_unicode_and_human_words_must_be_visible(edited, attack):
    report = {"title": "Original title", "markdown": "Literal e\u0301 🐝"}
    if edited:
        report["document_edits"] = {"markdown": "# Original title\nLiteral e\u0301 🐝"}
    text = "Original title\nLiteral e\u0301 🐝"
    contract.report_text(report, text)
    changed = text.replace(
        {"combining": "e\u0301", "emoji": "🐝", "title": "Original title"}[attack],
        "lost",
    )
    with pytest.raises(ValueError):
        contract.report_text(report, changed)


def test_command_keeps_reviewed_bootstrap_and_excludes_caller_accounts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-not-inherited")
    monkeypatch.setenv("SINTER_SESSION_KEY", "fictional-not-inherited")
    bootstrap = producer.seed_environment(tmp_path)
    bootstrap.setdefault("SystemRoot", "fictional-bootstrap")
    bootstrap["USERPROFILE"] = str(tmp_path)
    monkeypatch.setattr(
        producer, "seed_environment", lambda directory: bootstrap.copy()
    )
    original, observed = producer.subprocess.Popen, []

    def spawn(*args, **kwargs):
        observed.append(kwargs["env"].copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(producer.subprocess, "Popen", spawn)
    row = producer.command(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            "import sys;sys.stdout.buffer.write("
            "str(sys.flags.utf8_mode).encode() + b'\\n')",
        ],
        [],
        "utf8",
        tmp_path,
    )
    assert row["exit_code"] == 0 and contract.raw_blob(row["stdout"]) == b"1\n"
    assert observed[0]["SystemRoot"] == bootstrap["SystemRoot"]
    assert observed[0]["USERPROFILE"] == str(tmp_path)
    assert (
        "OPENAI_API_KEY" not in observed[0] and "SINTER_SESSION_KEY" not in observed[0]
    )


@pytest.mark.parametrize("role", contract.PACKAGE_ROLES)
def test_shared_exact_warning_only_belongs_to_final_candidate_removal(tmp_path, role):
    from tools import installed_native_entry_contract as shared

    rows, prior, candidate = package_rows()
    row = next(item for item in rows if item["role"] == role)
    row["stderr"] = contract.blob(shared.SHARED_OPT_REMOVAL_WARNING)
    folder = command_files(rows, tmp_path / "commands")
    if role == "remove":
        contract.package_commands(
            rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder
        )
    else:
        with pytest.raises(ValueError):
            contract.package_commands(
                rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder
            )


@pytest.mark.parametrize("change", ["duplicate", "different-path", "append"])
def test_removal_warning_cannot_hide_other_diagnostics(tmp_path, change):
    from tools import installed_native_entry_contract as shared

    raw = shared.SHARED_OPT_REMOVAL_WARNING
    raw = {
        "duplicate": raw * 2,
        "different-path": raw.replace(b"'/opt'", b"'/other'"),
        "append": raw + b"later failure\n",
    }[change]
    rows, prior, candidate = package_rows()
    rows[8]["stderr"] = contract.blob(raw)
    folder = command_files(rows, tmp_path / "commands")
    with pytest.raises(ValueError):
        contract.package_commands(
            rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder
        )


def test_actual_remove_helper_accepts_only_shared_warning_with_fixed_argv(
    tmp_path, monkeypatch
):
    from tools import installed_native_entry_contract as shared

    rows, _prior, _candidate = package_rows()
    row = rows[8]
    row["stderr"] = contract.blob(shared.SHARED_OPT_REMOVAL_WARNING)
    monkeypatch.setattr(producer, "command", lambda *args: row)
    producer.checked_package(["dpkg", "-r", "sinter"], [], "remove", tmp_path)
    with pytest.raises(ValueError):
        producer.checked_package(["dpkg", "-r", "other"], [], "remove", tmp_path)
    with pytest.raises(ValueError):
        producer.checked_package(["dpkg", "-r", "sinter"], [], "replace", tmp_path)


@pytest.mark.parametrize("role", contract.PACKAGE_ROLES)
@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_every_package_and_status_raw_stream_is_independently_bound(
    tmp_path, role, channel
):
    rows, prior, candidate = package_rows()
    folder = command_files(rows, tmp_path / "commands")
    contract.package_commands(rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder)
    path = folder / (role + "." + channel)
    path.write_bytes(path.read_bytes() + b"late raw failure after receipt\n")
    with pytest.raises(ValueError, match="sidecar"):
        contract.package_commands(
            rows, "0.5.4~rc3", "0.5.4~rc4", prior, candidate, folder
        )


def mapped_filesystem():
    prior = {
        "binary_sha256": "a" * 64,
        "binary_bytes": 10,
        "entries": {"sinter.desktop": contract.blob(b"prior browser")},
    }
    package = {
        "binary_sha256": "b" * 64,
        "binary_bytes": 11,
        "entries": {
            "sinter.desktop": contract.blob(b"new browser"),
            "sinter-native.desktop": contract.blob(b"new native"),
        },
    }
    receipt = {"filesystem": {}, "filesystem_commands": []}
    paths = [
        "/opt/neuroforge/sinter/Sinter",
        "/usr/share/applications/sinter.desktop",
        "/usr/share/applications/sinter-native.desktop",
    ]
    for index, phase in enumerate(("initial", "prior", "candidate", "removed")):
        payload = prior if phase == "prior" else package
        observed = {}
        for path in paths:
            if phase in {"initial", "removed"} or (
                phase == "prior" and path.endswith("sinter-native.desktop")
            ):
                observed[path] = {"exists": False, "errno": 2}
            else:
                entry = (
                    payload
                    if path.endswith("/Sinter")
                    else payload["entries"][PurePosixPath(path).name]
                )
                observed[path] = {
                    "exists": True,
                    "mode": stat.S_IFREG
                    | (0o755 if path.endswith("/Sinter") else 0o644),
                    "bytes": entry.get("binary_bytes", entry.get("bytes")),
                    "sha256": entry.get("binary_sha256", entry.get("sha256")),
                }
        receipt["filesystem"][phase] = observed
        receipt["filesystem_commands"].append(
            {
                "role": phase,
                "argv": [
                    "python3",
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    producer.FILESYSTEM_PROGRAM,
                ],
                "pid": 1000 + index,
                "exit_code": 0,
                "reaped": True,
                "stdout": contract.blob((contract.encoded(observed) + "\n").encode()),
                "stderr": contract.blob(b""),
            }
        )
    return receipt, package, prior


@pytest.mark.parametrize("phase", ["initial", "prior", "candidate", "removed"])
@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_every_filesystem_full_raw_stream_is_independently_bound(
    tmp_path, phase, channel
):
    receipt, package, prior = mapped_filesystem()
    folder = command_files(receipt["filesystem_commands"], tmp_path / "fs")
    contract.validate_filesystem(receipt, package, prior, folder)
    path = folder / (phase + "." + channel)
    path.write_bytes(path.read_bytes() + b"late raw filesystem failure\n")
    with pytest.raises(ValueError, match="sidecar"):
        contract.validate_filesystem(receipt, package, prior, folder)


@pytest.mark.parametrize("cleanup", ["context", "browser", "both"])
def test_ui_primary_error_survives_all_owned_cleanup_attempts(
    tmp_path, monkeypatch, cleanup
):
    calls = []

    class Context:
        pages = []

        def new_page(self):
            return SimpleNamespace(
                on=lambda *args: None,
                goto=lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError("first-body-error")
                ),
            )

        def route(self, *args):
            pass

        def close(self):
            calls.append("context")
            if cleanup in {"context", "both"}:
                raise RuntimeError("later-context-error")

    class Browser:
        def new_context(self, **kwargs):
            return Context()

        def close(self):
            calls.append("browser")
            if cleanup in {"browser", "both"}:
                raise RuntimeError("later-browser-error")

        def is_connected(self):
            return False

    class Manager:
        def __enter__(self):
            return SimpleNamespace(
                chromium=SimpleNamespace(launch=lambda **kwargs: Browser())
            )

        def __exit__(self, *args):
            calls.append("playwright")

    module = ModuleType("playwright.sync_api")
    module.expect = lambda *args: None
    module.sync_playwright = Manager
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    with pytest.raises(ValueError, match="first-body-error"):
        probe.ui(
            "http://127.0.0.1:1", {}, tmp_path, Path("fictional-chromium"), "0.5.4rc3"
        )
    diagnostics = json.loads((tmp_path / "ui-diagnostics.json").read_bytes())
    assert diagnostics["failure"] == "first-body-error"
    assert calls == ["context", "browser", "playwright"]
    assert diagnostics["cleanup_failures"]


@pytest.mark.parametrize("cleanup", ["shutdown", "owned-close", "both"])
def test_host_primary_error_survives_relay_cleanup_and_publishes_response(
    tmp_path, monkeypatch, cleanup
):
    calls = []
    expected = {"prior_version": "0.5.4rc3"}
    producer.write(tmp_path / "expected.json", expected)
    request = {
        "schema": "sinter-rc4-replacement-bridge/v1",
        "phase": "prior",
        "version": "0.5.4rc3",
        "pid": 1000,
        "port": 12345,
        "workspace": "/out/fixture",
        "binary_sha256": "a" * 64,
        "expected_sha256": contract.sha((tmp_path / "expected.json").read_bytes()),
        "collector_source_sha256": contract.sha(Path(probe.__file__).read_bytes()),
    }
    producer.write(tmp_path / "state.json", request)
    monkeypatch.setattr(Path, "is_socket", lambda path: path == tmp_path / "relay.sock")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(probe.tempfile, "tempdir", probe.tempfile.tempdir)

    class ShortMappedTemp:
        def __str__(self):
            return "/mapped/t"

        def __fspath__(self):
            return str(self)

        def is_absolute(self):
            return True

        def resolve(self):
            return self

        def is_dir(self):
            return True

        def iterdir(self):
            return iter(())

    class Relay:
        server_address = ("127.0.0.1", 1)
        errors = model_requests = 0
        close_failures = []

        def __init__(self, runtime):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            calls.append("shutdown")
            if cleanup in {"shutdown", "both"}:
                raise RuntimeError("later-shutdown-error")

        def close_owned(self):
            calls.append("owned-close")
            if cleanup in {"owned-close", "both"}:
                raise RuntimeError("later-owned-close-error")
            return 0, 0

        def idle(self):
            return True

    monkeypatch.setattr(probe, "HostRelay", Relay)
    monkeypatch.setattr(probe, "closed_port", lambda port: 111)
    monkeypatch.setattr(
        probe,
        "ui",
        lambda *args: (_ for _ in ()).throw(RuntimeError("first-host-error")),
    )
    with pytest.raises(ValueError, match="first-host-error"):
        probe.collect(tmp_path, Path("fictional-chromium"), "prior", ShortMappedTemp())
    response = json.loads((tmp_path / "response.json").read_bytes())
    diagnostics = json.loads((tmp_path / "host-diagnostics.json").read_bytes())
    assert response["request"] == request and response["failure"] == "first-host-error"
    assert (
        diagnostics["failure"] == "first-host-error" and diagnostics["cleanup_failures"]
    )
    assert calls == ["shutdown", "owned-close"]


@pytest.mark.parametrize("name", ["host", "ui", "inner"])
def test_bridge_refuses_a_retained_primary_or_cleanup_failure(
    tmp_path, monkeypatch, name
):
    bridge, process, expected, workspace, folder, runtime = mapped_bridge(
        tmp_path, monkeypatch
    )
    path = (
        folder / "inner-diagnostics.json"
        if name == "inner"
        else runtime / (name + "-diagnostics.json")
    )
    diagnostics = json.loads(path.read_bytes())
    diagnostics["cleanup_failures"] = ["actual later cleanup failure"]
    producer.write(path, diagnostics)
    with pytest.raises(ValueError, match="diagnostics"):
        contract.validate_bridge(bridge, process, expected, "prior", workspace, folder)


def test_normal_saved_document_wording_and_quoted_claims_remain_visible():
    report = {
        "title": "Saved enquiry",
        "markdown": "é 🐝",
        "document_markdown": "# Saved enquiry\n\n"
        "> Earlier source says all dates confirmed.\n\n"
        "Venue permission remains unknown. 🐝",
    }
    text = "Saved enquiry\nEarlier source says all dates confirmed.\n"
    text += "Venue permission remains unknown. 🐝"
    contract.report_text(report, text)
    with pytest.raises(ValueError, match="wording"):
        contract.report_text(report, "Saved enquiry\n🐝")


def visible_semantics_fixture():
    campaign = {
        "actions": [
            {
                "task": "Check permission",
                "owner": "Morgan Example",
                "owner_kind": "unknown",
                "due": "2026-10-09",
            },
            {"task": "Check water", "owner": "", "owner_kind": "unassigned", "due": ""},
        ]
    }
    facts = [
        {"label": label, "text": value, "visible": True}
        for label, value in [
            ("Application window", "Not checked"),
            ("Application lead", "Application process not confirmed"),
            ("Decision timing", "Not confirmed"),
        ]
    ]
    owners = []
    for index, row in enumerate(campaign["actions"]):
        owners.append(
            {
                "index": index,
                "task": row["task"],
                "visible": True,
                "summary": "Owner type not confirmed: Morgan Example"
                if index == 0
                else "No person named; owner needed",
                "detail": "Confirm whether this entry is a named person or a "
                "suggested role before recording acceptance."
                if index == 0
                else "Owner needed — no person is recorded. Assign a named "
                "person before marking acceptance.",
                "owner_type_label": "Type needs confirmation"
                if index == 0
                else "No owner assigned",
                "date_text": "Proposed target: 9 Oct 2026. "
                "Confirm timing with the owner."
                if index == 0
                else "No target date set. Confirm timing with the owner.",
            }
        )
    visible = {
        "owner_semantics_capability": "conservative owner fields",
        "opportunity_facts": facts,
        "owner_semantics": owners,
        "campaign": "\n".join(row["label"] + "\n" + row["text"] for row in facts),
        "actions": "\n".join(
            row[key]
            for row in owners
            for key in ("task", "summary", "detail", "date_text")
        ),
    }
    return visible, campaign


@pytest.mark.parametrize(
    "change",
    [
        "campaign-promoted",
        "actions-promoted",
        "window-field-promoted",
        "decision-promoted",
        "owner-summary-promoted",
        "owner-detail-promoted",
        "owner-hidden",
        "date-promoted",
        "modern-fields-dropped",
        "legacy-relabel",
    ],
)
def test_actual_visible_semantic_fields_cannot_promote_unknowns(change):
    visible, campaign = visible_semantics_fixture()
    # A source quotation can use these words without becoming current semantic facts.
    visible["campaign"] += (
        "\nHistorical quotation: all dates confirmed and application OPEN."
    )
    contract.visible_campaign_semantics(visible, campaign, "0.5.4rc3")
    if change == "campaign-promoted":
        visible["campaign"] = "All dates confirmed; application OPEN."
    elif change == "actions-promoted":
        visible["actions"] = "All owners assigned and confirmed."
    elif change == "window-field-promoted":
        visible["opportunity_facts"][0]["text"] = "OPEN"
    elif change == "decision-promoted":
        visible["opportunity_facts"][2]["text"] = "Confirmed"
    elif change == "owner-summary-promoted":
        visible["owner_semantics"][1]["summary"] = "Owner assigned and confirmed"
    elif change == "owner-detail-promoted":
        visible["owner_semantics"][0]["detail"] = "Acceptance confirmed"
    elif change == "owner-hidden":
        visible["owner_semantics"][1]["visible"] = False
    elif change == "modern-fields-dropped":
        visible.pop("owner_semantics")
    elif change == "legacy-relabel":
        visible["owner_semantics_capability"] = "legacy fields only"
    else:
        visible["owner_semantics"][1]["date_text"] = "Confirmed due date"
    with pytest.raises(ValueError):
        contract.visible_campaign_semantics(visible, campaign, "0.5.4rc3")


@pytest.mark.parametrize("change", ["status", "remaining-path"])
def test_known_warning_does_not_discharge_actual_status_or_path_absence(
    tmp_path, change
):
    from tools import installed_native_entry_contract as shared

    rows, prior_path, candidate_path = package_rows()
    rows[8]["stderr"] = contract.blob(shared.SHARED_OPT_REMOVAL_WARNING)
    if change == "status":
        rows[9]["stdout"] = contract.blob(b"install ok installed\n0.5.4~rc4\n")
    folder = command_files(rows, tmp_path / "commands")
    if change == "status":
        with pytest.raises(ValueError, match="absence"):
            contract.package_commands(
                rows, "0.5.4~rc3", "0.5.4~rc4", prior_path, candidate_path, folder
            )
        return
    contract.package_commands(
        rows, "0.5.4~rc3", "0.5.4~rc4", prior_path, candidate_path, folder
    )
    receipt, package, prior = mapped_filesystem()
    receipt["filesystem"]["removed"]["/opt/neuroforge/sinter/Sinter"] = {
        "exists": True,
        "mode": stat.S_IFREG | 0o755,
        "bytes": package["binary_bytes"],
        "sha256": package["binary_sha256"],
    }
    receipt["filesystem_commands"][-1]["stdout"] = contract.blob(
        contract.encoded(receipt["filesystem"]["removed"]).encode()
    )
    folder = command_files(receipt["filesystem_commands"], tmp_path / "fs")
    with pytest.raises(ValueError, match="absence"):
        contract.validate_filesystem(receipt, package, prior, folder)


@pytest.mark.parametrize("cleanup", ["shutdown", "owned-close"])
def test_inner_host_failure_keeps_first_error_and_publishes_bridge(
    tmp_path, monkeypatch, cleanup
):
    runtime, output = tmp_path / "bridge", tmp_path / "run"
    runtime.mkdir()
    output.mkdir()
    calls = []

    class Relay:
        close_failures = []

        def __init__(self, directory):
            (directory / "relay.sock").write_bytes(b"inert owned socket marker")

        def serve_forever(self):
            pass

        def shutdown(self):
            calls.append("shutdown")
            if cleanup == "shutdown":
                raise RuntimeError("later-inner-shutdown-error")

        def close_owned(self):
            calls.append("owned-close")
            if cleanup == "owned-close":
                raise RuntimeError("later-inner-close-error")
            return 0, 0

    original_write = probe.write

    def publish(path, value):
        original_write(path, value)
        if path.name == "state.json":
            calls.append("publish-once")
            original_write(
                runtime / "response.json",
                {
                    "request": value,
                    "ui": None,
                    "failure": "first-host-observer-error",
                    "resources": None,
                },
            )

    monkeypatch.setattr(probe, "InstalledRelay", Relay)
    monkeypatch.setattr(probe, "write", publish)
    with pytest.raises(ValueError, match="first-host-observer-error"):
        probe.hosted_ui(
            SimpleNamespace(port=12345),
            {"prior_version": "0.5.4rc3"},
            output,
            runtime,
            "prior",
            "0.5.4rc3",
            1000,
            PurePosixPath("/out/fixture"),
            "a" * 64,
        )
    bridge = json.loads((output / "bridge.json").read_bytes())
    diagnostics = json.loads((output / "inner-diagnostics.json").read_bytes())
    assert "first-host-observer-error" in bridge["failure"]
    assert "first-host-observer-error" in diagnostics["failure"]
    assert diagnostics["cleanup_failures"]
    assert calls == ["publish-once", "shutdown", "owned-close"]
    assert not (runtime / "relay.sock").exists()


@pytest.mark.parametrize(
    "kind", [stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFLNK]
)
@pytest.mark.parametrize(
    "guard", ["hashes", "snapshot", "package", "filesystem", "outer", "regular"]
)
def test_unlisted_special_entries_are_refused_before_any_read(
    tmp_path, monkeypatch, kind, guard
):
    rows, prior_path, candidate_path = package_rows()
    receipt, package, prior = mapped_filesystem()
    folder = command_files(
        rows if guard == "package" else receipt["filesystem_commands"],
        tmp_path / "evidence",
    )
    path = folder / "unlisted-special"
    path.write_bytes(b"inert special-entry type control")
    original = Path.lstat

    def metadata(item, *args, **kwargs):
        if item == path:
            return SimpleNamespace(st_mode=kind)
        return original(item, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", metadata)

    def action():
        if guard == "hashes":
            return producer.hashes(folder)
        if guard == "snapshot":
            return contract.snapshot(folder)
        if guard == "package":
            return contract.package_commands(
                rows, "0.5.4~rc3", "0.5.4~rc4", prior_path, candidate_path, folder
            )
        if guard == "filesystem":
            return contract.validate_filesystem(receipt, package, prior, folder)
        if guard == "outer":
            return contract.outer_sidecars([], folder)
        return contract.regular(path)

    with pytest.raises(ValueError, match="regular"):
        action()


def test_legacy_prior_owner_capability_cannot_claim_newer_semantics():
    visible = {
        "campaign": "Application closes\nNot confirmed\nDecision timing\nNot confirmed",
        "opportunity_facts": [
            {"label": "Application closes", "text": "Not confirmed", "visible": True},
            {"label": "Decision timing", "text": "Not confirmed", "visible": True},
        ],
        "owner_semantics_capability": "legacy fields only",
        "owner_semantics": [],
        "owner_types": [],
        "owner_acceptance": [],
    }
    contract.visible_campaign_semantics(visible, {}, "0.5.3")
    visible["owner_semantics"] = [{"confirmed": True}]
    with pytest.raises(ValueError, match="Legacy"):
        contract.visible_campaign_semantics(visible, {}, "0.5.3")


@pytest.mark.parametrize(
    "reference,actual",
    [
        (
            "First confirm permission.\nThen invite attendees.",
            "Then invite attendees. First confirm permission.",
        ),
        (
            "## First section\nKeep this qualification.\n"
            "## Second section\nKeep this qualification.",
            "Second section Keep this qualification. "
            "First section Keep this qualification.",
        ),
        ("Do not proceed.\nDo not proceed.", "Do not proceed."),
        (
            "Before.\nRepeat.\nMiddle.\nRepeat.\nAfter.",
            "Before. Repeat. Repeat. Middle. After.",
        ),
    ],
)
@pytest.mark.parametrize("human_edit", [False, True])
def test_complete_saved_wording_preserves_order_and_multiplicity(
    reference, actual, human_edit
):
    report = {"title": "Review", "document_markdown": "# Review\n" + reference}
    if human_edit:
        report["document_edits"] = {"markdown": "# Applied human heading\n" + reference}
    wording = report.get("document_edits", {}).get(
        "markdown", report["document_markdown"]
    )
    contract.report_text(
        report,
        "Review controls " + contract.rendered_document(wording) + " Export controls",
    )
    altered = ("Applied human heading " if human_edit else "") + actual
    with pytest.raises(ValueError, match="ordered"):
        contract.report_text(report, "Review controls " + altered + " Export controls")


@pytest.mark.parametrize("failing", ["diagnostic", "fallback", "all"])
def test_ui_publication_failure_preserves_first_exception_and_unpublished_bytes(
    tmp_path, monkeypatch, failing
):
    calls = []
    first = RuntimeError("FIRST-UI-BODY")

    class Context:
        pages = []

        def new_page(self):
            return SimpleNamespace(
                on=lambda *args: None,
                goto=lambda *args, **kwargs: (_ for _ in ()).throw(first),
            )

        def route(self, *args):
            pass

        def close(self):
            calls.append("context")
            raise RuntimeError("LATER-CONTEXT")

    class Browser:
        def new_context(self, **kwargs):
            return Context()

        def close(self):
            calls.append("browser")

        def is_connected(self):
            return False

    class Manager:
        def __enter__(self):
            return SimpleNamespace(
                chromium=SimpleNamespace(launch=lambda **kwargs: Browser())
            )

        def __exit__(self, *args):
            calls.append("driver")

    fake = ModuleType("playwright.sync_api")
    fake.expect = lambda *args: None
    fake.sync_playwright = Manager
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    real_write = probe.write
    attempted = []

    def publishing(path, value):
        attempted.append(path.name)
        if (
            failing == "all"
            or (failing == "diagnostic" and path.name == "ui-diagnostics.json")
            or (failing == "fallback" and path.name == "ui-failed-response.json")
        ):
            raise OSError("WRITE-FAILED:" + path.name)
        real_write(path, value)

    monkeypatch.setattr(probe, "write", publishing)
    with pytest.raises(probe.EvidenceFailure, match="FIRST-UI-BODY") as caught:
        probe.ui(
            "http://127.0.0.1:1", {}, tmp_path, Path("fictional-chromium"), "0.5.4rc3"
        )
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert calls == ["context", "browser", "driver"]
    assert attempted == ["ui-diagnostics.json", "ui-failed-response.json"]
    assert any("LATER-CONTEXT" in text for text in error.cleanup_errors)
    assert error.publication_errors and error.unpublished_bytes
    for path, raw in error.unpublished_bytes.items():
        payload = json.loads(raw)
        assert payload.get("failure", payload.get("first_failure")) == "FIRST-UI-BODY"
        assert path not in error.published_paths
    if failing == "diagnostic":
        fallback = json.loads((tmp_path / "ui-failed-response.json").read_bytes())
        for path, raw in error.unpublished_bytes.items():
            row = fallback["unpublished_bytes"][path]
            assert base64.b64decode(row["data_base64"]) == raw
            assert row["bytes"] == len(raw) and row["sha256"] == contract.sha(raw)
    else:
        assert not (tmp_path / "ui-failed-response.json").exists()


@pytest.mark.parametrize("failing", ["diagnostic", "response", "both", "all"])
def test_host_publications_are_independent_and_cannot_acknowledge_incomplete_evidence(
    tmp_path, monkeypatch, failing
):
    first = RuntimeError("FIRST-HOST-BODY")
    expected = {"prior_version": "0.5.4rc3"}
    producer.write(tmp_path / "expected.json", expected)
    producer.write(
        tmp_path / "state.json",
        {
            "schema": "sinter-rc4-replacement-bridge/v1",
            "phase": "prior",
            "version": "0.5.4rc3",
            "pid": 1000,
            "port": 12345,
            "workspace": "/out/fixture",
            "binary_sha256": "a" * 64,
            "expected_sha256": contract.sha((tmp_path / "expected.json").read_bytes()),
            "collector_source_sha256": contract.sha(Path(probe.__file__).read_bytes()),
        },
    )
    monkeypatch.setattr(Path, "is_socket", lambda path: path == tmp_path / "relay.sock")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(probe.tempfile, "tempdir", probe.tempfile.tempdir)

    class Temp:
        def __str__(self):
            return "/mapped/t"

        def __fspath__(self):
            return str(self)

        def is_absolute(self):
            return True

        def resolve(self):
            return self

        def is_dir(self):
            return True

        def iterdir(self):
            return iter(())

    calls = []

    class Relay:
        server_address = ("127.0.0.1", 1)
        errors = model_requests = 0
        close_failures = []

        def __init__(self, *args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            calls.append("shutdown")

        def close_owned(self):
            calls.append("close")
            raise RuntimeError("LATER-RELAY-CLOSE")

        def idle(self):
            return True

    monkeypatch.setattr(probe, "HostRelay", Relay)
    monkeypatch.setattr(probe, "closed_port", lambda port: 111)
    monkeypatch.setattr(probe, "ui", lambda *args: (_ for _ in ()).throw(first))
    real_write = probe.write
    attempted = []

    def publishing(path, value):
        attempted.append(path.name)
        blocked = (
            {"host-diagnostics.json"}
            if failing == "diagnostic"
            else {"response.json"}
            if failing == "response"
            else {"host-diagnostics.json", "response.json"}
        )
        if failing == "all" or path.name in blocked:
            raise OSError("WRITE-FAILED:" + path.name)
        real_write(path, value)

    monkeypatch.setattr(probe, "write", publishing)
    with pytest.raises(probe.EvidenceFailure, match="FIRST-HOST-BODY") as caught:
        probe.collect(tmp_path, Path("fictional-chromium"), "prior", Temp())
    error = caught.value
    assert error.primary_exception is first and error.__cause__ is first
    assert calls == ["shutdown", "close"]
    assert attempted == [
        "host-diagnostics.json",
        "response.json",
        "host-failed-response.json",
    ]
    assert any("LATER-RELAY-CLOSE" in text for text in error.cleanup_errors)
    for path, raw in error.unpublished_bytes.items():
        payload = json.loads(raw)
        assert "FIRST-HOST-BODY" in str(
            payload.get("failure", payload.get("first_failure"))
        )
        assert path not in error.published_paths
    if failing == "diagnostic":
        response = json.loads((tmp_path / "response.json").read_bytes())
        assert (
            "FIRST-HOST-BODY" in response["failure"]
            and "WRITE-FAILED" in response["failure"]
        )
    if failing != "all":
        fallback = json.loads((tmp_path / "host-failed-response.json").read_bytes())
        for path, raw in error.unpublished_bytes.items():
            assert (
                base64.b64decode(fallback["unpublished_bytes"][path]["data_base64"])
                == raw
            )
    else:
        assert not (tmp_path / "host-failed-response.json").exists()


def test_ordered_saved_segments_allow_rendered_list_labels_but_not_reordering():
    report = {
        "title": "Review",
        "document_markdown": "# Review\n1. First confirm permission.\n"
        "2. Then invite attendees.",
    }
    contract.report_text(
        report, "DRAFT Review\n1. First confirm permission.\n2. Then invite attendees."
    )
    with pytest.raises(ValueError, match="ordered"):
        contract.report_text(
            report,
            "DRAFT Review\n1. Then invite attendees.\n2. First confirm permission.",
        )


def test_repeated_saved_segments_cannot_share_a_visible_word_occurrence():
    report = {"title": "Review", "document_markdown": "A\nA"}
    contract.report_text(report, "Review A A")
    with pytest.raises(ValueError, match="ordered"):
        contract.report_text(report, "Review AA")


def test_host_cli_retains_unpublished_utf8_bytes_in_owned_stderr(tmp_path, monkeypatch):
    first = RuntimeError("FIRST-HOST e\u0301 🐝")
    monkeypatch.setattr(
        probe, "write", lambda *args: (_ for _ in ()).throw(OSError("write denied"))
    )
    publisher = probe.EvidencePublisher("HOST", first, [])
    publisher.attempt(tmp_path / "host-diagnostics.json", {"failure": str(first)})
    with pytest.raises(probe.EvidenceFailure) as failed:
        publisher.finish(tmp_path / "host-failed-response.json")
    error = failed.value
    monkeypatch.setattr(probe, "collect", lambda *args: (_ for _ in ()).throw(error))
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="ascii", errors="strict")
    monkeypatch.setattr(probe.sys, "stderr", stream)
    with pytest.raises(SystemExit) as stopped:
        probe.main(
            [
                "--runtime",
                str(tmp_path),
                "--chromium",
                "fictional-chromium",
                "--browser-tmp",
                "/mapped/t",
                "--phase",
                "prior",
            ]
        )
    assert stopped.value.code == 1 and stopped.value.__cause__ is error
    record = json.loads(buffer.getvalue().decode("utf-8"))
    assert record["first_failure"] == str(first)
    assert record["published_paths"] == []
    assert len(record["publication_errors"]) == 2
    for path, raw in error.unpublished_bytes.items():
        row = record["unpublished_bytes"][path]
        assert base64.b64decode(row["data_base64"]) == raw
        assert row["bytes"] == len(raw) and row["sha256"] == contract.sha(raw)
