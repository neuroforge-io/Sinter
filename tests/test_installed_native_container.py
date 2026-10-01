"""Owning lifecycle controls; only inert Python byte/probe children are run here."""

import json
import os
import sys
from types import SimpleNamespace

import pytest
from test_installed_native_entry_contract import (
    inner_fixture,
    outer_fixture,
    output,
    stream,
)

from tools import installed_native_container as outer
from tools import installed_native_entry_contract as contract
from tools import installed_native_menu as inner


def mutate(bundle, index, update):
    raw = contract.stream_bytes(bundle["commands"][index]["stdout"])
    value = json.loads(raw)
    update(value[0])
    bundle["commands"][index]["stdout"] = stream(output(value))


@pytest.mark.parametrize(
    "attack",
    [
        "empty_finish",
        "nonsense_finish",
        "offset_finish",
        "bad_date",
        "too_many_nanos",
        "zero_finish",
        "missing_finish",
        "reversed_time",
        "missing_oom",
        "integer_oom",
        "string_oom",
        "missing_error",
        "bool_error",
        "integer_error",
        "bool_created_pid",
        "bool_exit_pid",
        "bool_exit_code",
        "integer_running",
        "bool_created_exit",
        "already_started",
        "wrong_actual_args",
    ],
)
def test_actual_raw_lifecycle_types_and_real_utc_timestamps_are_closed(attack):
    bundle, pins = outer_fixture()
    index = (
        2
        if attack in {"bool_created_pid", "bool_created_exit", "already_started"}
        else 4
    )

    def update(row):
        state = row["State"]
        if attack == "empty_finish":
            state["FinishedAt"] = ""
        elif attack == "nonsense_finish":
            state["FinishedAt"] = "invented finished claim"
        elif attack == "offset_finish":
            state["FinishedAt"] = "2026-10-02T00:00:00+00:00"
        elif attack == "bad_date":
            state["FinishedAt"] = "2026-02-30T00:00:00Z"
        elif attack == "too_many_nanos":
            state["FinishedAt"] = "2026-10-02T00:00:00.1234567890Z"
        elif attack == "zero_finish":
            state["FinishedAt"] = "0001-01-01T00:00:00Z"
        elif attack == "missing_finish":
            state.pop("FinishedAt")
        elif attack == "reversed_time":
            state["StartedAt"] = "2026-10-02T00:00:01Z"
        elif attack == "missing_oom":
            state.pop("OOMKilled")
        elif attack == "integer_oom":
            state["OOMKilled"] = 0
        elif attack == "string_oom":
            state["OOMKilled"] = ""
        elif attack == "missing_error":
            state.pop("Error")
        elif attack == "bool_error":
            state["Error"] = False
        elif attack == "integer_error":
            state["Error"] = 0
        elif attack in {"bool_created_pid", "bool_exit_pid"}:
            state["Pid"] = False
        elif attack in {"bool_exit_code", "bool_created_exit"}:
            state["ExitCode"] = False
        elif attack == "integer_running":
            state["Running"] = 0
        elif attack == "already_started":
            state["StartedAt"] = "2026-10-02T00:00:00Z"
        else:
            row["Args"][-1] = "/unowned/directory"

    mutate(bundle, index, update)
    with pytest.raises(ValueError):
        contract.validate_outer(bundle, pins)


@pytest.mark.parametrize(
    "prefix", ["Error: No such object: ", "error: no such object: "]
)
def test_known_original_docker_absence_grammars_bind_exact_full_id(prefix):
    bundle, pins = outer_fixture()
    original = (prefix + "2" * 64 + "\n").encode()
    bundle["commands"][6]["stderr"] = stream(original)
    assert contract.validate_outer(bundle, pins) == "2" * 64
    assert contract.stream_bytes(bundle["commands"][6]["stderr"]) == original


@pytest.mark.parametrize(
    "raw",
    [
        b"permission denied\n",
        b"Cannot connect to the Docker daemon\n",
        b"error: no such object: " + b"2" * 63 + b"\n",
        b"error: no such object: " + b"3" * 64 + b"\n",
        b"error: no such object: " + b"2" * 64 + b"\nextra",
        b"ERROR: NO SUCH OBJECT: " + b"2" * 64 + b"\n",
    ],
)
def test_query_failures_or_loose_case_matching_cannot_prove_removal(raw):
    bundle, pins = outer_fixture()
    bundle["commands"][6]["stderr"] = stream(raw)
    with pytest.raises(ValueError):
        contract.validate_outer(bundle, pins)


@pytest.mark.parametrize("field", ["display", "removal"])
def test_redundant_inner_exit_summaries_keep_integer_meaning(tmp_path, field):
    receipt, source, package, pins = inner_fixture(tmp_path)
    if field == "display":
        receipt["display"]["stdout_observed"]["exit_code"] = False
    else:
        receipt["removal"]["command_exit"] = False
    with pytest.raises(ValueError):
        contract.validate_inner(receipt, source, package, 7, pins)


@pytest.mark.skipif(
    not hasattr(os, "killpg"),
    reason="Requires an actual POSIX process-group byte capture.",
)
def test_full_original_stream_files_survive_beyond_the_bounded_prefix(tmp_path):
    rows = []
    stdout = tmp_path / "full.stdout"
    stderr = tmp_path / "full.stderr"
    payload = b"x" * 65536 + b" exact hidden tail\xff\n"
    code, raw = inner.command(
        [
            sys.executable,
            "-B",
            "-c",
            "import sys;sys.stdout.buffer.write(b'x'*65536+b' exact hidden tail\\xff\\n')",
        ],
        rows,
        limit=100000,
        save_streams={"stdout": stdout, "stderr": stderr},
    )
    assert (
        code == 0
        and raw == payload
        and stdout.read_bytes() == payload
        and stderr.read_bytes() == b""
    )
    assert (
        rows[0]["stdout"]["sha256"] == contract.sha(payload)
        and rows[0]["stdout"]["truncated"] is True
    )
    assert rows[0]["streams_complete"] is True


def test_missing_review_pin_refuses_before_any_owned_resource_or_docker_call(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(outer.platform, "system", lambda: "Linux")
    target = tmp_path / "unused"
    monkeypatch.setattr(
        outer, "capture", lambda *_a, **_k: pytest.fail("No command before source pin")
    )
    with pytest.raises(ValueError, match="review pin"):
        outer.prepare(
            SimpleNamespace(mode="mechanics", output=target, owner_sha256="0" * 64)
        )
    assert not target.exists()


def test_missing_matching_package_refuses_without_a_container(tmp_path, monkeypatch):
    monkeypatch.setattr(outer.platform, "system", lambda: "Linux")
    target = tmp_path / "unused"
    expected = contract.sha((outer.ROOT / outer.SOURCE_FILE).read_bytes())
    monkeypatch.setattr(
        outer,
        "capture",
        lambda *_a, **_k: pytest.fail("No Docker or install without exact inputs"),
    )
    with pytest.raises(ValueError, match="requires exact source/package"):
        outer.prepare(SimpleNamespace(mode="run", output=target, owner_sha256=expected))
    assert not target.exists()


def test_mechanics_uses_one_fixed_source_command_and_never_native_installer_argv(
    tmp_path,
):
    pins = outer.pins_for(tmp_path, "a" * 64)
    argv = outer.mechanics_argv(pins, "sinter-native-entry-abcdefghijkl")
    assert argv[-4:] == [
        "python3",
        "-B",
        "/source/tools/installed_native_container.py",
        "_mechanics_inside",
    ]
    assert (
        "installed_native_menu.py" not in json.dumps(argv)
        and "--entrypoint" not in argv
    )
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--workdir") + 1] == "/" and outer.IMAGE_ID in argv
    assert "--privileged" not in argv and "--pull" not in argv


def test_installed_bundle_cannot_be_spoofed_as_mechanics():
    bundle, pins = outer_fixture()
    with pytest.raises(ValueError, match="mechanics-only"):
        outer.validate_mechanics(bundle, pins)


@pytest.mark.parametrize("failure", ["start_deadline", "body_exit", "created_inspect"])
def test_owned_cleanup_targets_only_actual_id_and_keeps_primary_failure(
    tmp_path, monkeypatch, failure
):
    identifier = "2" * 64
    fixture, pins = outer_fixture()
    pins.update(outer.pins_for(tmp_path, "a" * 64))
    observed = json.loads(contract.stream_bytes(fixture["commands"][2]["stdout"]))[0]
    observed["Image"] = outer.IMAGE_ID
    name = "sinter-native-entry-abcdef012345"
    observed["Name"] = "/" + name
    command = outer.mechanics_argv(pins, name)
    observed["Config"]["Cmd"] = command[command.index(outer.IMAGE_ID) + 1 :]
    observed["Args"] = command[command.index(outer.IMAGE_ID) + 2 :]
    for mount in observed["Mounts"]:
        key = {
            "/source": "source_directory",
            "/repository": "repository",
            "/candidate": "candidate_directory",
            "/out": "output_directory",
        }[mount["Destination"]]
        mount["Source"] = pins[key]
    monkeypatch.setattr(outer.secrets, "token_hex", lambda _n: "abcdef012345")
    commands = []
    client_rows = []
    cleanup_rows = []
    calls = []

    def row(role, argv, *_args, **_kwargs):
        calls.append((role, argv))
        commands.append({"role": role, "argv": argv})
        if role == "image":
            return 0, output(
                [{"Id": outer.IMAGE_ID, "Os": "linux", "Architecture": "amd64"}]
            )
        if role == "create":
            return 0, (identifier + "\n").encode()
        if role == "created" and failure == "created_inspect":
            raise ValueError("Exact created inspection failure")
        if role == "created":
            return 0, output([observed])
        if role == "start" and failure == "start_deadline":
            raise TimeoutError("Exact owned deadline")
        if role == "start":
            return 7, b"Exact producer error"
        if role == "exited":
            return 0, output([{"State": {"Running": False, "Status": "exited"}}])
        if role == "removed":
            return 1, b"[]\n"
        return 0, b""

    def capture(role, argv, *_args, **_kwargs):
        calls.append((role, argv))
        return 0, b""

    monkeypatch.setattr(outer, "docker_row", row)
    monkeypatch.setattr(contract, "validate_removal", lambda *_args: None)
    monkeypatch.setattr(outer, "capture", capture)
    with pytest.raises((TimeoutError, ValueError), match="Exact|producer failed"):
        outer.lifecycle(
            tmp_path,
            {},
            pins,
            commands,
            client_rows,
            mechanics=True,
            cleanup_rows=cleanup_rows,
        )
    cleanup = [
        argv
        for role, argv in calls
        if role.startswith("cleanup") or role in {"remove", "removed"}
    ]
    assert cleanup and all(argv[-1] == identifier for argv in cleanup)
    assert not any("prune" in argv or "--all" in argv for argv in cleanup)
    assert next(argv for role, argv in calls if role == "remove") == (
        ["docker", "rm", identifier]
        if failure == "body_exit"
        else ["docker", "rm", "-f", identifier]
    )


def test_output_ancestor_alias_refuses_before_copy_or_command(tmp_path, monkeypatch):
    monkeypatch.setattr(outer.platform, "system", lambda: "Linux")
    expected = contract.sha((outer.ROOT / outer.SOURCE_FILE).read_bytes())
    with pytest.raises(ValueError, match="outside"):
        outer.prepare(
            SimpleNamespace(
                mode="mechanics",
                output=outer.ROOT / "unused-outer-output",
                owner_sha256=expected,
            )
        )


def test_nanosecond_lifecycle_order_is_not_truncated_to_microseconds():
    bundle, pins = outer_fixture()
    mutate(
        bundle,
        4,
        lambda row: row["State"].update(
            StartedAt="2026-10-02T00:00:00.123456789Z",
            FinishedAt="2026-10-02T00:00:00.123456788Z",
        ),
    )
    with pytest.raises(ValueError, match="out of order"):
        contract.validate_outer(bundle, pins)


def test_source_snapshot_refuses_import_caches_and_redirects(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/installed_native_container.py").write_bytes(b"owned")
    (tmp_path / "__pycache__").mkdir()
    with pytest.raises(ValueError, match="import caches"):
        outer.source_records(tmp_path)


def test_prestart_predicate_refuses_created_raw_before_any_native_command(tmp_path):
    bundle, pins = outer_fixture()
    created = json.loads(contract.stream_bytes(bundle["commands"][2]["stdout"]))[0]
    created["State"]["Pid"] = False
    with pytest.raises(ValueError, match="created State"):
        contract.validate_container_observation(
            created,
            pins,
            contract.outer_argv,
            "sinter-native-entry-abcdefghijkl",
            "2" * 64,
            "created",
        )


def test_cleanup_absence_predicate_cannot_accept_a_permission_error():
    bundle, _pins = outer_fixture()
    bundle["commands"][6]["stderr"] = stream(b"permission denied\n")
    with pytest.raises(ValueError, match="arbitrary inspection failure"):
        contract.validate_removal(
            bundle["commands"][5], bundle["commands"][6], "2" * 64
        )


def test_git_trust_cannot_expand_beyond_owned_readonly_repository():
    bundle, pins = outer_fixture()

    def change(row):
        row["Config"]["Env"] = [
            value.replace("GIT_CONFIG_VALUE_0=/repository", "GIT_CONFIG_VALUE_0=*")
            for value in row["Config"]["Env"]
        ]

    mutate(bundle, 2, change)
    with pytest.raises(ValueError, match="Git source read"):
        contract.validate_outer(bundle, pins)


@pytest.mark.parametrize(
    "paths",
    [
        None,
        {},
        {
            key: None if key == "git" else "/usr/bin/" + key
            for key in outer.REQUIRED_TOOLS
        },
        {
            key: False if key == "git" else "/usr/bin/" + key
            for key in outer.REQUIRED_TOOLS
        },
    ],
)
def test_claimed_tooling_boolean_cannot_replace_original_tool_observations(paths):
    with pytest.raises(ValueError, match="lacks installed-owner tooling"):
        outer.require_installed_tooling(
            {"installed_tooling_available": True, "actual_tool_paths": paths}
        )


def test_shared_lifecycle_accepts_only_the_trusted_callers_exact_fifth_mount():
    bundle, pins = outer_fixture()
    pins["prior_directory"] = "/owned/prior"
    spec = contract.DEFAULT_MOUNT_SPEC + (("prior_directory", "/prior", False),)

    def fixed_creation(pins, name):
        argv = contract.outer_argv(pins, name)
        index = argv.index("--env")
        return (
            argv[:index]
            + [
                "--mount",
                "type=bind,src=" + pins["prior_directory"] + ",dst=/prior,readonly",
            ]
            + argv[index:]
        )

    bundle["commands"][1]["argv"] = fixed_creation(
        pins, "sinter-native-entry-abcdefghijkl"
    )
    for index in (2, 4):
        mutate(
            bundle,
            index,
            lambda row: row["Mounts"].append(
                {
                    "Type": "bind",
                    "Source": pins["prior_directory"],
                    "Destination": "/prior",
                    "RW": False,
                }
            ),
        )
    assert (
        contract.validate_lifecycle(bundle["commands"], pins, fixed_creation, spec)[
            "container_id"
        ]
        == "2" * 64
    )
    with pytest.raises(ValueError):
        contract.validate_outer(bundle, pins)
    pins["prior_directory"] = pins["output_directory"] + "/aliased-prior"
    with pytest.raises(ValueError, match="disjoint"):
        contract.validate_lifecycle(bundle["commands"], pins, fixed_creation, spec)


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_actual_unsupported_host_refuses_before_any_resource(
    tmp_path, monkeypatch, system
):
    target = tmp_path / "must-stay-absent"
    monkeypatch.setattr(outer.platform, "system", lambda: system)
    monkeypatch.setattr(
        outer,
        "capture",
        lambda *_a, **_k: pytest.fail("No command on unsupported host"),
    )
    monkeypatch.setattr(
        outer,
        "source_records",
        lambda *_a, **_k: pytest.fail("No source copy on unsupported host"),
    )
    with pytest.raises(ValueError, match="Linux host only"):
        outer.prepare(
            SimpleNamespace(mode="mechanics", output=target, owner_sha256="0" * 64)
        )
    assert not target.exists()
