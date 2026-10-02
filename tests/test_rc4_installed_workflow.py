"""SOURCE ownership controls only: no Docker, installer, app or real browser.

Ordinary Python child capture is real. Projected fixture identities are never
submitted to the original installed admission or represented as installed proof.
"""

from __future__ import annotations

import ast
import base64
import copy
import io
import json
import os
import sys
import tempfile
import types
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_rc4_native_publication import envelope_owned_directory

from tools import rc4_installed_workflow as producer
from tools import rc4_installed_workflow_contract as contract


def input_fixture():
    return {
        "schema": contract.CONFIG,
        "version": contract.VERSION,
        "source_commit": "a" * 40,
        "owner_sha256": "b" * 64,
        "qa_files": {
            contract.SOURCE_FILE: {"bytes": 1, "sha256": "b" * 64},
            contract.CONTRACT_FILE: {"bytes": 1, "sha256": "c" * 64},
        },
        "installer_name": "Sinter-0.5.4rc4-linux-x64.deb",
        "package_receipt_name": "Sinter-0.5.4rc4-linux-x64-test.json",
        "installer_sha256": "d" * 64,
        "package_receipt_sha256": "e" * 64,
        "uid": 1000,
        "gid": 1000,
        "repository": str(Path("fictional/source").resolve()),
        "browser": {
            "path": str(Path("fictional/chromium").resolve()),
            "sha256": "f" * 64,
        },
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("version", "0.5.4rc4.dev0"),
        ("version", "0.5.4rc3"),
        ("source_commit", "a" * 39),
        ("source_commit", "A" * 40),
        ("owner_sha256", "0" * 64),
        ("installer_sha256", "d" * 63),
        ("installer_name", "candidate.deb"),
        ("package_receipt_name", "other.json"),
        ("uid", True),
        ("uid", -1),
        ("uid", 2**31),
        ("gid", 1000.0),
        ("repository", "relative"),
        ("browser", {"path": "/fake", "sha256": "f" * 64, "fallback": True}),
    ],
)
def test_input_refuses_dev_projection_unknown_roles_and_weak_pins(key, value):
    inputs = input_fixture()
    assert contract.config(inputs) is inputs
    changed = copy.deepcopy(inputs)
    changed[key] = value
    with pytest.raises(ValueError):
        contract.config(changed)


def test_exact_input_and_inspection_fields():
    inputs = input_fixture()
    inputs["automatic_retry"] = True
    with pytest.raises(ValueError):
        contract.config(inputs)
    assert contract.read_json_list(b'[{"Id":"fictional"}]') == [{"Id": "fictional"}]
    for raw in (b"[]", b"[{},{}]", b'[{"Id":1,"Id":2}]', b'[{"Id":NaN}]', b"{}"):
        with pytest.raises(ValueError):
            contract.read_json_list(raw)


@pytest.mark.parametrize(
    "name,row",
    [
        ("../source", {"bytes": 1, "sha256": "a" * 64}),
        ("/source", {"bytes": 1, "sha256": "a" * 64}),
        ("src//alias", {"bytes": 1, "sha256": "a" * 64}),
        ("src/example", {"bytes": True, "sha256": "a" * 64}),
        ("src/example", {"bytes": -1, "sha256": "a" * 64}),
        ("src/example", {"bytes": contract.MAX_FILE + 1, "sha256": "a" * 64}),
        ("src/example", {"bytes": 1, "sha256": "a" * 64, "admitted": True}),
    ],
)
def test_source_inventory_refuses_before_any_command(name, row):
    inputs = input_fixture()
    inputs["qa_files"][name] = row
    with pytest.raises(ValueError):
        contract.config(inputs)


def test_fixed_owned_argv_has_network_none_five_mounts_and_observed_user(tmp_path):
    from tools import installed_native_container as owner

    inputs = input_fixture()
    pins = owner.pins_for(
        tmp_path,
        inputs["owner_sha256"],
        inputs["source_commit"],
        inputs["installer_name"],
        inputs["package_receipt_name"],
    )
    pins["workflow_directory"] = str(tmp_path / "runtime")
    argv = contract.outer_argv(pins, "sinter-native-entry-123456abcdef")
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv.count("--mount") == 5
    assert argv[-4:] == ["python3", "-B", "/source/" + contract.SOURCE_FILE, "inner"]
    assert "type=bind,src=" + str(tmp_path / "runtime") + ",dst=/proof" in argv
    assert contract.exec_argv("1" * 64, inputs) == [
        "docker",
        "exec",
        "--user",
        "1000:1000",
        "1" * 64,
        "python3",
        "-B",
        "/source/" + contract.SOURCE_FILE,
        "controller",
    ]
    assert not any(
        "--privileged" in value or "--cap-add" in value or "chown" in value
        for value in argv
    )
    for identifier in ("", "alias", "1" * 63, "1" * 65):
        with pytest.raises(ValueError):
            contract.exec_argv(identifier, inputs)


@pytest.mark.parametrize("primary", [False, True])
def test_every_cleanup_attempt_runs_and_first_actual_exception_survives(primary):
    first, second = RuntimeError("first actual fault"), OSError("second actual fault")
    attempts = producer.Attempts(first if primary else None)
    called = []

    def fail(error):
        called.append(str(error))
        raise error

    attempts.call("stdout", lambda: fail(second if primary else first))
    attempts.call("stderr", lambda: fail(second))
    attempts.call("independent absence", lambda: called.append("independent absence"))
    with pytest.raises(RuntimeError) as raised:
        attempts.raise_first()
    assert raised.value is first
    assert called[-1] == "independent absence"
    assert [row["resource"] for row in attempts.rows] == [
        "stdout",
        "stderr",
        "independent absence",
    ]
    assert len(attempts.errors) == 2 and attempts.rows[-1]["succeeded"] is True


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "killpg"),
    reason="Actual child process-group observation requires POSIX os.killpg.",
)
def test_real_ordinary_child_full_streams_are_conserved_after_reap(tmp_path):
    from tools import installed_native_menu as menu

    out, err = b"retained stdout\n" * 8000, b"retained diagnostic\n" * 6000
    rows = []
    argv = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        "-c",
        "import os;os.write(1,b'retained stdout\\n'*8000);os.write(2,b'retained diagnostic\\n'*6000)",
    ]
    menu.command(
        argv,
        rows,
        limit=contract.MAX_FILE,
        save_streams={
            name: tmp_path / ("child." + name) for name in ("stdout", "stderr")
        },
    )
    contract.command(rows[0], argv)
    contract.streams(rows[0], tmp_path / "child")
    assert (tmp_path / "child.stdout").read_bytes() == out
    assert (tmp_path / "child.stderr").read_bytes() == err
    assert (
        rows[0]["streams_complete"] is True
        and rows[0]["owned_group_remaining"] is False
    )
    assert rows[0]["stdout"]["truncated"] is True
    (tmp_path / "child.stderr").write_bytes(err + b"changed")
    with pytest.raises(ValueError, match="stream"):
        contract.streams(rows[0], tmp_path / "child")


@pytest.mark.parametrize("failed_at", ["second stream", "child spawn"])
def test_partial_app_acquisition_closes_every_acquired_stream(
    tmp_path, monkeypatch, failed_at
):
    from tools import rc4_installed_recovery as recovery

    monkeypatch.setattr(
        recovery,
        "owned_inner_relay",
        lambda root: SimpleNamespace(serve_forever=lambda: None),
    )
    (tmp_path / "process").mkdir()
    controller = producer.Controller(tmp_path, {})
    opened, ordinary_open = [], Path.open
    first = OSError("inert acquisition failure")

    def open_stream(path, *args, **kwargs):
        if args == ("xb",) and path.name in {"stdout", "stderr"}:
            if failed_at == "second stream" and path.name == "stderr":
                raise first
            stream = ordinary_open(path, *args, **kwargs)
            opened.append(stream)
            return stream
        return ordinary_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_stream)

    def no_child(*args, **kwargs):
        raise first

    monkeypatch.setattr(producer.subprocess, "Popen", no_child)
    with pytest.raises(OSError) as raised:
        controller.launch(1)
    assert raised.value is first and opened and all(stream.closed for stream in opened)
    assert controller.process is None and controller.rows == []
    assert all(row["succeeded"] is True for row in controller.acquisition_cleanup)


def test_controller_thread_start_fault_still_closes_and_retains_all_resources(
    tmp_path, monkeypatch
):
    from tools import rc4_installed_recovery as recovery

    # This SOURCE controller projects Linux metadata; it never starts an app.
    monkeypatch.setattr(producer.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(producer.os, "getegid", lambda: 1000, raising=False)

    ordinary_read = contract.regular
    monkeypatch.setattr(
        contract,
        "regular",
        lambda path, limit: (
            b"SOURCE\0inert-controller\0"
            if Path(path) == Path("/proc/self/cmdline")
            else ordinary_read(path, limit)
        ),
    )

    called = []
    first = RuntimeError("SOURCE inert thread start failure")
    relay = SimpleNamespace(
        serve_forever=lambda: None,
        idle=lambda: True,
        shutdown=lambda: called.append("shutdown"),
        server_close=lambda: called.append("close"),
    )
    monkeypatch.setattr(recovery, "owned_inner_relay", lambda root: relay)
    controller = producer.Controller(tmp_path, {})

    def start():
        raise first

    controller.thread = SimpleNamespace(
        start=start, is_alive=lambda: False, join=lambda **kwargs: called.append("join")
    )
    with pytest.raises(RuntimeError) as raised:
        controller.run()
    assert raised.value is first and called == ["close"]
    retained = producer.read_json(tmp_path / "controller.json")
    assert retained["failure"]["message"] == str(first)
    assert len(retained["cleanup_attempts"]) == 6 and retained["resources"] == {
        "inner_thread_closed": True,
        "inner_requests_closed": True,
        "inner_socket_absent": True,
        "app_groups_absent": True,
    }


def test_controller_metadata_read_fault_is_retained_without_start_or_masking(
    tmp_path, monkeypatch
):
    from tools import rc4_installed_recovery as recovery

    # This SOURCE controller projects Linux metadata; it never starts an app.
    monkeypatch.setattr(producer.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(producer.os, "getegid", lambda: 1000, raising=False)

    first, called = OSError("SOURCE controller cmdline read failed"), []
    relay = SimpleNamespace(
        serve_forever=lambda: None,
        idle=lambda: True,
        shutdown=lambda: called.append("shutdown"),
        server_close=lambda: called.append("close"),
    )
    monkeypatch.setattr(recovery, "owned_inner_relay", lambda root: relay)
    controller = producer.Controller(tmp_path, {})
    controller.thread = SimpleNamespace(
        start=lambda: called.append("start"),
        is_alive=lambda: False,
        join=lambda **kwargs: None,
    )
    ordinary_read = contract.regular

    def read(path, limit):
        if Path(path) == Path("/proc/self/cmdline"):
            raise first
        return ordinary_read(path, limit)

    monkeypatch.setattr(contract, "regular", read)
    with pytest.raises(OSError) as raised:
        controller.run()
    assert raised.value is first and called == ["close"]
    retained = producer.read_json(tmp_path / "controller.json")
    assert retained["cmdline"] is None and retained["failure"]["message"] == str(first)


@pytest.mark.parametrize("stop_fault", [False, True])
@pytest.mark.parametrize(
    "diagnostics",
    [
        "exact",
        "missing",
        "changed",
        "extra",
        "wrong_port",
        "extra_notice",
        "wrong_opener",
        "wrong_listener",
    ],
)
def test_app_reap_retains_both_original_streams_and_independent_listener(
    tmp_path, monkeypatch, stop_fault, diagnostics
):
    from tools import native_window_smoke as native
    from tools import rc4_installed_recovery as recovery

    monkeypatch.setattr(
        recovery,
        "owned_inner_relay",
        lambda root: SimpleNamespace(serve_forever=lambda: None, port=12345),
    )
    folder = tmp_path / "process/run-1"
    folder.mkdir(parents=True)
    notice = b"SOURCE inert browser-mode notice\n"
    controller = producer.Controller(
        tmp_path, {"notice_base64": base64.b64encode(notice).decode()}
    )
    controller.paths = {name: folder / name for name in ("stdout", "stderr")}
    controller.streams = {
        name: path.open("xb") for name, path in controller.paths.items()
    }
    opener = b"http://127.0.0.1:12345"
    banner = b"Sinter local workspace: http://127.0.0.1:12345\n"
    if diagnostics == "wrong_listener":
        opener = opener.replace(b"12345", b"12346")
        banner = banner.replace(b"12345", b"12346")
    observed_stdout = {
        "missing": b"",
        "changed": banner.replace(b"workspace", b"Workspace"),
        "extra": banner + b"extra\n",
        "wrong_port": banner.replace(b"12345", b"12346"),
    }.get(diagnostics, banner)
    observed_stderr = notice + (b"extra\n" if diagnostics == "extra_notice" else b"")
    controller.streams["stdout"].write(observed_stdout)
    controller.streams["stderr"].write(observed_stderr)
    controller.process = SimpleNamespace(poll=lambda: 0)
    argv = [contract.BINARY, "app", "--mode", "browser", "--directory", "/proof/data"]
    controller.rows = [
        {
            "run": 1,
            "argv": argv,
            "pid": 23456,
            "sigterm_sent": False,
            "forced_cleanup": False,
            "stop_method": "interface_quit",
            "opener": contract.full_record(
                opener + (b"\n" if diagnostics == "wrong_opener" else b"")
            ),
            "port": 12346 if diagnostics == "wrong_listener" else 12345,
        }
    ]
    observed = []
    first = RuntimeError("inert reap failure")

    def stop(process, row):
        row.update(exit_code=0, owned_group_remaining=False)
        if stop_fault:
            raise first

    monkeypatch.setattr(native, "stop_process", stop)
    monkeypatch.setattr(
        producer, "closed_port", lambda port: observed.append(port) or True
    )
    if stop_fault:
        with pytest.raises(RuntimeError) as raised:
            controller.reap()
        assert raised.value is first
    elif diagnostics == "exact":
        controller.reap()
        assert producer.read_json(tmp_path / "state.json")["phase"] == "stopped"
    else:
        with pytest.raises(ValueError):
            controller.reap()
        assert not (tmp_path / "state.json").exists()
    assert observed == [12345] and all(
        stream.closed for stream in controller.streams.values()
    )
    assert controller.paths["stdout"].read_bytes() == observed_stdout
    assert controller.paths["stderr"].read_bytes() == observed_stderr
    retained = producer.read_json(folder / "observation.json")
    contract.streams(retained, folder, directory=True)
    assert len(retained["cleanup_observation"]["attempts"]) == 6
    assert len(retained["cleanup_observation"]["errors"]) == int(stop_fault)


def zip_fixture(files, *, commit="a" * 40, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.comment = commit.encode()
        parents = {
            parent.as_posix()
            for name in files
            for parent in Path(name).parents
            if str(parent) != "."
        }
        for name in sorted(parents):
            entry = zipfile.ZipInfo(name + "/")
            entry.external_attr = 0o40775 << 16
            archive.writestr(entry, b"")
        for name, raw in files.items():
            entry = zipfile.ZipInfo(name)
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
        if extra:
            entry, raw = extra
            archive.writestr(entry, raw)
    return output.getvalue()


def test_source_zip_requires_exact_complete_regular_bounded_roles(monkeypatch):
    files = {"src/example.txt": b"fictional source\n"}
    qa = {name: contract.record(raw) for name, raw in files.items()}
    raw = zip_fixture(files)
    producer.validate_zip(raw, "a" * 40, qa)
    with pytest.raises(ValueError, match="origin"):
        producer.validate_zip(raw, "b" * 40, qa)
    for name in (
        "../outside",
        "/absolute",
        "src//alias",
        "src/extra",
        "src/example.txt",
    ):
        entry = zipfile.ZipInfo(name)
        entry.external_attr = 0o100644 << 16
        if name == "src/example.txt":
            with pytest.warns(UserWarning, match="Duplicate name"):
                malformed = zip_fixture(files, extra=(entry, b"extra"))
        else:
            malformed = zip_fixture(files, extra=(entry, b"extra"))
        with pytest.raises(ValueError):
            producer.validate_zip(malformed, "a" * 40, qa)
    entry = zipfile.ZipInfo("linked")
    entry.external_attr = 0o120777 << 16
    with pytest.raises(ValueError, match="non-regular"):
        producer.validate_zip(
            zip_fixture(files, extra=(entry, b"target")), "a" * 40, qa
        )
    monkeypatch.setattr(contract, "MAX_FILE", 1)
    with pytest.raises(ValueError, match="bound"):
        producer.validate_zip(raw, "a" * 40, qa)


def test_existing_ui_body_old_cleanup_masks_primary_new_explicit_owner_preserves_it(
    monkeypatch, tmp_path
):
    """Run the unchanged body up to acquisition failure with inert browser APIs."""
    from tools import _support
    from tools import installed_workflow_browser as workflow
    from tools.rc4_installed_recovery import OwnedBrowserSession

    first, cleanup = (
        RuntimeError("SOURCE UI acquisition failed"),
        OSError("SOURCE browser close failed"),
    )
    closes = []

    class Browser:
        def new_context(self, **kwargs):
            raise first

        def close(self):
            closes.append("browser")
            raise cleanup

    browser = Browser()
    driver = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))

    class Manager:
        def __enter__(self):
            return driver

        def __exit__(self, *args):
            closes.append("driver")
            return False

    inert = types.ModuleType("playwright.sync_api")
    inert.sync_playwright = Manager
    inert.expect = lambda *args: None
    monkeypatch.setitem(sys.modules, "playwright.sync_api", inert)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setattr(_support, "launch_chromium", lambda *args: browser)
    args = SimpleNamespace(
        output=tmp_path, chromium="/inert/chrome", version=contract.VERSION
    )
    relay = SimpleNamespace(server_address=("127.0.0.1", 12345))
    # OLD RED: the default raw browser close replaces the actual UI failure.
    with pytest.raises(OSError) as old:
        workflow.browser_workflow(args, tmp_path, relay, {}, [])
    assert old.value is cleanup
    closes.clear()
    # NEW GREEN: the explicitly supplied accepted owner preserves the UI failure
    # while attempting browser final close and driver close independently.
    session = OwnedBrowserSession("core-workflow")
    with pytest.raises(RuntimeError) as new:
        workflow.browser_workflow(
            args, tmp_path, relay, {}, [], browser_session=session
        )
    assert (
        new.value is first and closes[-1] == "driver" and closes.count("browser") >= 2
    )
    assert session.observations()["cleanup_errors"] and session.driver_closed is True


def test_real_browser_dependency_is_not_replaced_by_inert_test_api(monkeypatch):
    import builtins

    from tools.rc4_installed_recovery import OwnedBrowserSession

    ordinary_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ModuleNotFoundError("SOURCE optional Playwright intentionally absent")
        return ordinary_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ModuleNotFoundError, match="intentionally absent"):
        OwnedBrowserSession("core-workflow").__enter__()


@pytest.mark.parametrize("cleanup_fault", [False, True])
def test_captured_driver_acquisition_fault_preserves_candidates_and_primary(
    tmp_path, monkeypatch, cleanup_fault
):
    from tools import rc4_native_handoff as handoff

    observed = iter(({7}, {7, 21, 22}))
    monkeypatch.setattr(handoff, "children", lambda: next(observed))
    closes = []

    class Manager:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *args):
            closes.append("driver")
            if cleanup_fault:
                raise OSError("SOURCE inert driver close failure")
            return False

    inert = types.ModuleType("playwright.sync_api")
    inert.sync_playwright = Manager
    monkeypatch.setitem(sys.modules, "playwright.sync_api", inert)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    session = producer.captured_session_class()(tmp_path, Path("/inert/chrome"))
    with pytest.raises(ValueError, match="One actual continuing"):
        session.__enter__()
    assert closes == ["driver"] and session.driver_observation == {
        "candidates": [21, 22]
    }
    assert session.driver_closed is (not cleanup_fault)
    assert len(session.observations()["cleanup_errors"]) == int(cleanup_fault)


def test_original_ui_contract_positives_and_no_invoked_operations_claim():
    from tools.installed_workflow_contract import (
        workflow_artifact_paths,
        workflow_checks,
    )
    from tools.installed_workflow_qualification import source_operations

    source = {
        path.relative_to(producer.ROOT).as_posix(): path.read_bytes()
        for path in producer.ROOT.rglob("*")
        if path.is_file()
    }
    operations = source_operations(source)
    assert len(operations) in {53, 54}
    assert ("campaigns.funding_summary" in {row["id"] for row in operations}) is (
        len(operations) == 54
    )
    assert len(workflow_checks(source)) == 22
    roles = workflow_artifact_paths(source)
    assert (
        len(roles) == 13
        and len(
            [
                name
                for name, path in roles.items()
                if name.startswith("word_copy_") and path.endswith(".docx")
            ]
        )
        == 3
    )
    parsed = ast.parse((producer.ROOT / contract.SOURCE_FILE).read_text())
    calls = [
        node
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "browser_workflow"
    ]
    assert len(calls) == 1 and [key.arg for key in calls[0].keywords] == [
        "browser_session"
    ]
    assert (
        producer.captured_session_class().__mro__[1].__name__ == "OwnedBrowserSession"
    )


def catalogue_alignment_source(count):
    raw = (producer.ROOT / "src/sinter/runtime.py").read_bytes()
    if count == 54:
        return {"src/sinter/runtime.py": raw}
    assert count == 53
    tree = ast.parse(raw)
    entries = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_OPERATIONS"
            for target in node.targets
        )
    )
    entries.elts = [
        entry
        for entry in entries.elts
        if entry.args[0].value != "campaigns.funding_summary"
    ]
    return {"src/sinter/runtime.py": ast.unparse(tree).encode()}


@pytest.mark.parametrize("count", [53, 54])
def test_workflow_returned_catalogue_count_comes_from_trusted_source(count):
    from tools.installed_workflow_qualification import source_operations

    source = catalogue_alignment_source(count)
    operations = source_operations(source)
    assert len(operations) == count
    tree = ast.parse((producer.ROOT / contract.CONTRACT_FILE).read_bytes())
    verifier = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_original"
    )
    result = next(
        node.value
        for node in verifier.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in node.targets
        )
    )
    expression = next(
        value
        for key, value in zip(result.keys, result.values)
        if key.value == "operations_catalogue"
    )
    declared = eval(
        compile(ast.Expression(expression), contract.CONTRACT_FILE, "eval"),
        {"source_operations": source_operations, "source_bytes": source},
    )
    assert type(declared) is int and declared == count


def catalogue_alignment_envelope(source):
    from tools.installed_workflow_qualification import source_operations

    return {
        "schema": "sinter-operation-result/v1",
        "version": contract.VERSION,
        "operation": "operations",
        "ok": True,
        "result": {
            "schema": "sinter-operations/v1",
            "version": contract.VERSION,
            "operations": source_operations(source),
            "excluded": [
                "account setup",
                "credentials",
                "settings mutations",
                "HTTP session/security controls",
                "desktop lifecycle",
            ],
            "jobs": "Temporary within one Runtime; CLI waits and never starts a daemon."
            " Save/export useful results explicitly.",
        },
    }


@pytest.mark.parametrize("count", [53, 54])
@pytest.mark.parametrize(
    "field", ["id", "method", "route", "summary", "input", "effect"]
)
def test_catalogue_alignment_keeps_all_exact_installed_definition_fields(count, field):
    from tools.installed_workflow_qualification import validate_operations_catalog

    source = catalogue_alignment_source(count)
    envelope = catalogue_alignment_envelope(source)
    validate_operations_catalog(envelope, source, contract.VERSION)
    envelope["result"]["operations"][0][field] = "changed-actual-installed-definition"
    with pytest.raises(ValueError, match="exact .*operation source contract"):
        validate_operations_catalog(envelope, source, contract.VERSION)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "duplicate-id",
        "missing-with-funding",
        "funding-id",
        "method",
        "route",
        "effect",
    ],
)
def test_catalogue_alignment_has_only_closed_source_profiles(mutation):
    from tools.installed_workflow_qualification import source_operations

    source = catalogue_alignment_source(54)
    tree = ast.parse(source["src/sinter/runtime.py"])
    entries = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_OPERATIONS"
            for target in node.targets
        )
    )
    funding = next(
        entry
        for entry in entries.elts
        if entry.args[0].value == "campaigns.funding_summary"
    )
    if mutation == "extra":
        extra = copy.deepcopy(entries.elts[0])
        extra.args[0] = ast.Constant("unrecognized.extra")
        entries.elts.append(extra)
    elif mutation == "duplicate-id":
        funding.args[0] = copy.deepcopy(entries.elts[0].args[0])
    elif mutation == "missing-with-funding":
        entries.elts.pop(0)
    elif mutation == "funding-id":
        funding.args[0] = ast.Constant("unrecognized.funding")
    else:
        index = {"method": 1, "route": 2, "effect": 5}[mutation]
        if index == 5:
            funding.args.append(ast.Constant("other-effect"))
        else:
            funding.args[index] = ast.Constant("other-definition")
    source["src/sinter/runtime.py"] = ast.unparse(tree).encode()
    with pytest.raises(ValueError):
        source_operations(source)


@pytest.mark.parametrize("count", [53, 54])
def test_fixture_catalogue_alignment_preserves_original_practice_result(count):
    from tools.installed_workflow_contract import PRACTICE_FILES

    source = {
        name: (producer.ROOT / name).read_bytes()
        for name in (
            *PRACTICE_FILES,
            "src/sinter/web/offline-garden-casebook.json",
            "src/sinter/web/offline-garden-campaign.json",
        )
    }
    source.update(catalogue_alignment_source(count))
    original = copy.deepcopy(source)
    result = producer.fixture(source)
    assert source == original
    assert set(result) == {"casebook", "campaign", "source", "practice_hashes", "web"}
    assert result["source"] is source
    assert result["practice_hashes"] == {
        name: contract.sha(source[name]) for name in PRACTICE_FILES
    }
    assert result["web"] == {
        name: contract.sha(raw)
        for name, raw in source.items()
        if name.startswith("src/sinter/web/")
    }


def test_unfinished_receipt_uses_exact_existing_unicode_json_digests(tmp_path):
    from tools.installed_workflow_browser import object_digest

    inputs = input_fixture()
    source = {
        path.relative_to(producer.ROOT).as_posix(): path.read_bytes()
        for path in producer.ROOT.rglob("*")
        if path.is_file()
    }
    frozen = {"machine": "SOURCE inert x64", "pointer_bits": 64, "frozen": True}
    ready = {
        "frozen_test": frozen,
        "binary_sha256": "1" * 64,
        "web": {"src/sinter/web/inert": "Unicode é"},
        "os_release": {"ID": "ubuntu", "VERSION_ID": "22.04"},
        "libc": ["glibc", "2.35"],
    }
    source_zip, receipt = tmp_path / "source.zip", tmp_path / "receipt.json"
    source_zip.write_bytes(b"SOURCE inert draft identity only")
    producer.write_json(receipt, {"installed_test": frozen})
    draft = producer.receipt(inputs, source, ready, source_zip, receipt)
    fictional = producer.fixture(source)
    assert draft["passed"] is False and not any(draft["resources"].values())
    assert draft["input_hashes"] == {
        "garden_casebook": object_digest(fictional["casebook"]),
        "garden_campaign": object_digest(fictional["campaign"]),
        "static_assets": object_digest(ready["web"]),
    }


def test_cli_help_needs_no_runtime_or_installer():
    parser, args = producer.arguments(
        [
            "verify",
            "--proof-root",
            "/inert/proof",
            "--source-commit",
            "a" * 40,
            "--owner-sha256",
            "b" * 64,
            "--installer-sha256",
            "c" * 64,
            "--package-receipt-sha256",
            "d" * 64,
        ]
    )
    assert args.mode == "verify" and "run" in parser.format_help()


def test_failed_atomic_delivery_retains_temporary_bytes(tmp_path, monkeypatch):
    final = tmp_path / "observation.json"
    first = OSError("SOURCE final evidence delivery failed")

    def refuse(*args):
        raise first

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError) as raised:
        producer.write_json(final, {"failure": "retained"})
    assert raised.value is first and not final.exists()
    assert json.loads(final.with_name(final.name + ".pending").read_bytes()) == {
        "failure": "retained"
    }


def test_unreadable_directory_is_not_silently_omitted_from_original_inventory(
    tmp_path, monkeypatch
):
    from tools import installed_workflow_contract as workflow

    monkeypatch.setattr(workflow, "workflow_artifact_paths", lambda source: {})
    (tmp_path / "source").mkdir()
    (tmp_path / "source/sentinel").write_bytes(b"s")
    (tmp_path / "out/evidence").mkdir(parents=True)
    producer.write_json(tmp_path / "out/evidence/inner.json", {"commands": []})
    blocked = tmp_path / "out/diagnostic-home"
    blocked.mkdir()
    ordinary = Path.iterdir

    def observed(path):
        if path == blocked:
            raise PermissionError("SOURCE unreadable diagnostic home")
        return ordinary(path)

    monkeypatch.setattr(Path, "iterdir", observed)
    inputs = {
        "qa_files": {"sentinel": contract.record(b"s")},
        "installer_name": "candidate.deb",
        "package_receipt_name": "candidate.json",
    }
    with pytest.raises(PermissionError, match="unreadable diagnostic home"):
        producer.validate_inventory(tmp_path, inputs)


# The controls below exercise only the exact source boundaries. They never run
# Git, Docker, a browser, the app, a provider, packaging or installed admission.
def test_nonprivileged_uid_refuses_root_but_preserves_numeric_gid_policy():
    inputs = input_fixture()
    inputs["uid"] = 0
    with pytest.raises(ValueError):
        contract.config(inputs)
    with pytest.raises(ValueError):
        contract.exec_argv("1" * 64, inputs)
    for uid in (1, 1000, 2**31 - 1):
        inputs["uid"], inputs["gid"] = uid, 0
        assert contract.config(inputs) is inputs
        assert contract.exec_argv("1" * 64, inputs)[3] == f"{uid}:0"


def test_root_producer_refuses_before_preparation_observation(tmp_path, monkeypatch):
    from tools import rc4_installed_recovery as recovery

    called = []
    monkeypatch.setattr(producer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(producer.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(recovery, "source_records", lambda *_: called.append("source"))
    with pytest.raises(ValueError, match="UID 0"):
        producer.prepare(SimpleNamespace(output=tmp_path / "untouched"))
    assert called == [] and not (tmp_path / "untouched").exists()


@pytest.fixture
def source_prepare_root():
    # The actual Linux preparation guard uses POSIX ownership and a <=55-byte
    # socket path. Keep the owned SOURCE fixture short independently of HOME,
    # pytest's basetemp and runner UID; do not bypass that production guard.
    if os.name != "posix" or not hasattr(os, "geteuid"):
        pytest.skip("Actual preparation ownership control requires POSIX metadata.")
    if os.geteuid() == 0:
        pytest.skip("The installed preparation owner deliberately refuses UID 0.")
    with tempfile.TemporaryDirectory(prefix="wf-", dir="/tmp") as directory:
        parent = Path(directory)
        assert parent.stat().st_uid == os.geteuid()
        assert not parent.stat().st_mode & 0o022
        assert len(os.fsencode(parent / "p/t")) <= 55
        yield parent / "p"


def _source_prepare_fault(tmp_path, monkeypatch, first, output):
    from tools import installed_native_menu as menu
    from tools import rc4_installed_recovery as recovery

    inputs = input_fixture()
    args = SimpleNamespace(
        owner_sha256=inputs["owner_sha256"],
        source_commit=inputs["source_commit"],
        repository=tmp_path / "repository",
        installer=tmp_path / "candidate.deb",
        package_receipt=tmp_path / "receipt.json",
        chromium=tmp_path / "chromium",
        output=output,
    )
    monkeypatch.setattr(producer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(recovery, "source_records", lambda *_: inputs["qa_files"])
    monkeypatch.setattr(recovery, "browser_identity", lambda *_: inputs["browser"])
    calls = []
    out, err = b"SOURCE raw Git stream\x00\xff\n" * 32, b"SOURCE actual refusal\n"

    def command(argv, rows, **kwargs):
        calls.append(argv)
        rows.append({"argv": argv, "partial": "SOURCE real refusal, not an admission"})
        kwargs["save_streams"]["stdout"].write_bytes(out)
        kwargs["save_streams"]["stderr"].write_bytes(err)
        raise first

    monkeypatch.setattr(menu, "command", command)
    return args, calls, out, err


def _final_boundary(namespace):
    tree = ast.parse(Path(producer.__file__).read_bytes())
    run = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run"
    )
    index = next(
        i
        for i, node in enumerate(run.body)
        if isinstance(node, ast.Try)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "finalize_workflow"
            for call in ast.walk(node)
        )
    )
    module = ast.Module(body=copy.deepcopy(run.body[index:-1]), type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(module), "<exact SOURCE final boundary>", "exec"
        ),
        namespace,
    )


def _failed_bytes(error, path, raw):
    record = error.as_record()["unpublished_bytes"][str(path)]
    assert record["bytes"] == len(raw)
    assert record["sha256"] == contract.sha(raw)
    assert base64.b64decode(record["data_base64"], validate=True) == raw
    assert error.unpublished_bytes[str(path)] == raw


@pytest.mark.parametrize("kind", [RuntimeError, KeyboardInterrupt])
def test_prepare_successful_receipt_preserves_identical_body_error(
    tmp_path, monkeypatch, kind, source_prepare_root
):
    first = kind("SOURCE first Git refusal")
    args, calls, out, err = _source_prepare_fault(
        tmp_path, monkeypatch, first, source_prepare_root
    )
    with pytest.raises(kind) as raised:
        producer.prepare(args)
    assert raised.value is first and len(calls) == 1
    assert (args.output / "raw/source-tar.stdout").read_bytes() == out
    assert (args.output / "raw/source-tar.stderr").read_bytes() == err
    assert (
        producer.read_json(args.output / "raw/source-commands.json")["commands"][0][
            "argv"
        ]
        == calls[0]
    )
    assert not (args.output / "raw/source-commands.json.failed.json").exists()


@pytest.mark.parametrize("fallback_fails", [False, True])
def test_first_git_fault_and_every_later_publication_fault_retain_complete_bytes(
    tmp_path, monkeypatch, fallback_fails, source_prepare_root
):
    first = RuntimeError("SOURCE first Git fault")
    receipt_fault, fallback_fault = (
        OSError("SOURCE receipt fault"),
        KeyboardInterrupt("SOURCE fallback close fault"),
    )
    args, calls, out, err = _source_prepare_fault(
        tmp_path, monkeypatch, first, source_prepare_root
    )
    attempted = []
    actual_writer = producer.write_json

    def writer(path, value):
        attempted.append((Path(path), producer.serialized_receipt(value)))
        if len(attempted) == 1:
            raise receipt_fault
        if fallback_fails:
            raise fallback_fault
        actual_writer(path, value)

    monkeypatch.setattr(producer, "write_json", writer)
    with pytest.raises(producer.evidence.EvidenceFailure) as raised:
        producer.prepare(args)
    error = raised.value
    assert error.primary_exception is first and error.__cause__ is first
    assert len(calls) == 1 and len(attempted) == 2
    assert (args.output / "raw/source-tar.stdout").read_bytes() == out
    assert (args.output / "raw/source-tar.stderr").read_bytes() == err
    _failed_bytes(error, *attempted[0])
    assert [r["error_type"] for r in error.publication_errors] == (
        ["OSError", "KeyboardInterrupt"] if fallback_fails else ["OSError"]
    )
    if fallback_fails:
        _failed_bytes(error, *attempted[1])
        assert error.published_paths == ()
    else:
        assert error.published_paths == (str(attempted[1][0]),)
        fallback = producer.read_json(attempted[1][0])
        assert fallback["unpublished_bytes"][str(attempted[0][0])]["bytes"] == len(
            attempted[0][1]
        )
    assert not attempted[0][0].exists()


@pytest.mark.parametrize("body_fails", [True, False])
@pytest.mark.parametrize("delivery_fails", [True, False])
def test_exact_final_qualification_preserves_body_and_publication_outcomes(
    tmp_path, monkeypatch, body_fails, delivery_fails
):
    first, second = (
        RuntimeError("SOURCE first semantic refusal"),
        OSError("SOURCE final receipt refused"),
    )
    path = tmp_path / "workflow-owner.json"
    value, calls = {"passed": False}, []
    actual_writer = producer.write_json

    def finalize(*_):
        if body_fails:
            raise first

    def writer(path, value):
        calls.append((Path(path), producer.serialized_receipt(value)))
        if delivery_fails:
            raise second
        actual_writer(path, value)

    monkeypatch.setattr(producer, "write_json", writer)
    fake_contract = SimpleNamespace(
        verify_original=lambda *_args, **_kwargs: {"SOURCE": "inert semantic return"}
    )
    namespace = {
        "root": tmp_path,
        "inputs": {},
        "value": value,
        "proof_args": None,
        "contract": fake_contract,
        "finalize_workflow": finalize,
        "publish_receipt": producer.publish_receipt,
    }
    if delivery_fails:
        with pytest.raises(producer.evidence.EvidenceFailure) as raised:
            _final_boundary(namespace)
        error = raised.value
        assert error.primary_exception is (first if body_fails else second)
        assert error.__cause__ is error.primary_exception
        assert len(calls) == 2 and not path.exists() and error.published_paths == ()
        for attempted, raw in calls:
            _failed_bytes(error, attempted, raw)
        assert len(error.publication_errors) == 2
    elif body_fails:
        with pytest.raises(RuntimeError) as raised:
            _final_boundary(namespace)
        assert raised.value is first and len(calls) == 1
    else:
        _final_boundary(namespace)
        assert len(calls) == 1 and producer.read_json(path)["passed"] is True
    if body_fails:
        assert value["passed"] is False
        assert value["failure"] == {"type": "RuntimeError", "message": str(first)}


def test_unchanged_writer_and_diagnostic_serializer_have_identical_valid_unicode_bytes(
    tmp_path,
):
    value = {"SOURCE": "Warraburra — 日本語 🌻", "nested": {"actual": 1}}
    path = tmp_path / "ordinary.json"
    producer.write_json(path, value)
    assert path.read_bytes() == producer.serialized_receipt(value)
    assert not path.with_name(path.name + ".pending").exists()


def test_actual_rename_refusal_retains_pending_bytes_and_original_body(tmp_path):
    path = tmp_path / "receipt.json"
    path.mkdir()
    first = RuntimeError("SOURCE first body refusal")
    value = {"original": "SOURCE complete fictional receipt — 🌻", "passed": False}
    with pytest.raises(producer.evidence.EvidenceFailure) as raised:
        producer.publish_receipt("SOURCE rename", path, value, first)
    error = raised.value
    assert error.primary_exception is first and error.__cause__ is first
    assert error.publication_errors[0]["error_type"] in (
        "IsADirectoryError",
        "PermissionError",
    )
    raw = producer.serialized_receipt(value)
    _failed_bytes(error, path, raw)
    assert path.with_name(path.name + ".pending").read_bytes() == raw
    assert error.published_paths == (str(path.with_name(path.name + ".failed.json")),)
    assert path.is_dir()


@pytest.mark.parametrize("body_first", [True, False])
def test_genuine_kernel_write_and_close_faults_preserve_order_and_every_attempt(
    tmp_path, monkeypatch, body_first
):
    import os

    actual_open = Path.open
    first = None
    if body_first:
        try:
            os.read(-1, 1)
        except OSError as error:
            first = error
    observed, opened = [], []

    class KernelFaultStream:
        def __init__(self, path):
            self.stream = actual_open(path, "xb")
            opened.append(path)

        def __enter__(self):
            return self

        def write(self, raw):
            self.stream.write(raw)
            self.stream.flush()
            try:
                os.write(-1, raw)
            except OSError as error:
                observed.append(error)
                raise

        def __exit__(self, *_):
            fd = self.stream.fileno()
            self.stream.close()
            try:
                os.close(fd)
            except OSError as error:
                observed.append(error)
                raise

    def opener(path, mode="r", *args, **kwargs):
        if path.parent == tmp_path and mode == "xb":
            return KernelFaultStream(path)
        return actual_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opener)
    path, value = (
        tmp_path / "receipt.json",
        {"SOURCE": "full actual pending bytes", "passed": False},
    )
    with pytest.raises(producer.evidence.EvidenceFailure) as raised:
        producer.publish_receipt("SOURCE actual kernel faults", path, value, first)
    error = raised.value
    assert len(opened) == 2 and len(observed) == 4
    assert error.primary_exception is (first if body_first else observed[0])
    assert error.__cause__ is error.primary_exception
    assert len(error.publication_errors) == 4 and error.published_paths == ()
    assert producer.diagnostic_failures(observed[1]) == tuple(observed[:2])
    assert producer.diagnostic_failures(observed[3]) == tuple(observed[2:])
    for attempted in (path, path.with_name(path.name + ".failed.json")):
        raw = attempted.with_name(attempted.name + ".pending").read_bytes()
        _failed_bytes(error, attempted, raw)
    assert all(row["error_type"] == "OSError" for row in error.publication_errors)


def test_observer_never_absorbs_an_unrelated_prior_exception(tmp_path, monkeypatch):
    first = RuntimeError("SOURCE unrelated earlier caller exception")
    second = OSError("SOURCE actual delivery failure")

    def writer(*_):
        raise second

    monkeypatch.setattr(producer, "write_json", writer)
    try:
        raise first
    except RuntimeError:
        with pytest.raises(producer.evidence.EvidenceFailure) as raised:
            producer.publish_receipt(
                "SOURCE unrelated context", tmp_path / "receipt.json", {}, first
            )
    assert raised.value.primary_exception is first
    assert producer.diagnostic_failures(second) == (second,)
    assert len(raised.value.publication_errors) == 2


def test_actual_surrogate_owned_path_refusal_is_reversible_in_full_cli_failure(
    tmp_path, monkeypatch, capfd
):
    import os
    import signal

    # Actual filename-byte admission differs from OS family (APFS rejects
    # invalid UTF-8). The shared helper falls back only on genuine EILSEQ;
    # permissions/capacity faults still propagate as the identical exception.
    path = envelope_owned_directory(tmp_path, filesystem_byte=True)
    byte_name_admitted = os.name == "posix" and os.fsencode(path.name) == b"owned-\xff"
    # Own a second directory to refuse fallback on every filesystem. A normal
    # Unicode fallback path would otherwise validly publish on Windows/macOS.
    path.with_name(path.name + ".failed.json").mkdir()
    value = {
        "failure": {
            "message": "SOURCE refused "
            + str(path)
            + ("" if byte_name_admitted else "\udcff")
        },
        "passed": False,
    }
    first = RuntimeError("SOURCE first qualification failure")

    def run(*_):
        producer.publish_receipt("SOURCE owned byte filename", path, value, first)

    parser = SimpleNamespace(
        exit=lambda *_: (_ for _ in ()).throw(
            AssertionError("generic CLI error must not replace typed data")
        )
    )
    monkeypatch.setattr(
        producer, "arguments", lambda *_: (parser, SimpleNamespace(mode="run"))
    )
    monkeypatch.setattr(producer, "run", run)
    prior_handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit) as stopped:
        producer.main([])
    assert stopped.value.code == 1 and signal.getsignal(signal.SIGTERM) is prior_handler
    error = stopped.value.__cause__
    assert isinstance(error, producer.evidence.EvidenceFailure)
    assert error.primary_exception is first and error.__cause__ is first
    out, err = capfd.readouterr()
    assert out == ""
    envelope = json.loads(err)
    assert envelope["schema"] == "sinter-rc4-workflow-failed-evidence/v1"
    carried = base64.b64decode(envelope["unpublished_bytes"][str(path)]["data_base64"])
    assert carried == producer.serialized_receipt(value)
    assert json.loads(carried)["failure"]["message"] == value["failure"]["message"]
    assert "\udcff" in value["failure"]["message"]
    if byte_name_admitted:
        assert (
            os.fsencode(
                Path(
                    json.loads(carried)["failure"]["message"].split(
                        "SOURCE refused ", 1
                    )[1]
                ).name
            )
            == b"owned-\xff"
        )
    assert (
        envelope["published_paths"] == [] and len(envelope["publication_errors"]) == 2
    )


def test_cli_ordinary_body_error_keeps_existing_exit_and_stream(
    tmp_path, monkeypatch, capsys
):
    parser = __import__("argparse").ArgumentParser()
    monkeypatch.setattr(
        producer, "arguments", lambda *_: (parser, SimpleNamespace(mode="run"))
    )
    first = ValueError("SOURCE ordinary refusal")

    def run(*_):
        raise first

    monkeypatch.setattr(producer, "run", run)
    with pytest.raises(SystemExit) as raised:
        producer.main([])
    assert raised.value.code == 1
    out, err = capsys.readouterr()
    assert out == "" and err == "ValueError: SOURCE ordinary refusal\n"


def test_final_failed_publication_carries_full_primary_beyond_receipt_summary(
    tmp_path, monkeypatch
):
    message = "SOURCE full original exception — 日本語\n" * 3000
    first, second = RuntimeError(message), OSError("SOURCE receipt refused")
    calls, value = [], {"passed": False}

    def finalize(*_):
        calls.append("finalize once")
        raise first

    def writer(path, record):
        calls.append((Path(path), producer.serialized_receipt(record)))
        raise second

    monkeypatch.setattr(producer, "write_json", writer)
    namespace = {
        "root": tmp_path,
        "inputs": {},
        "value": value,
        "proof_args": None,
        "contract": contract,
        "finalize_workflow": finalize,
        "publish_receipt": producer.publish_receipt,
    }
    with pytest.raises(producer.evidence.EvidenceFailure) as raised:
        _final_boundary(namespace)
    error = raised.value
    assert error.primary_exception is first and error.__cause__ is first
    assert error.as_record()["first_failure"] == message
    assert value["failure"]["message"] == message[:4096]  # Original schema behaviour.
    assert calls[0] == "finalize once" and len(calls) == 3
    for path, raw in calls[1:]:
        _failed_bytes(error, path, raw)
    assert error.published_paths == () and len(error.publication_errors) == 2


@pytest.mark.parametrize(
    "opener,port",
    [
        ("http://127.0.0.1:12345/", 12345),
        (" http://127.0.0.1:12345", 12345),
        ("http://127.0.0.1:12345\n", 12345),
        ("http://localhost:12345", 12345),
        ("https://127.0.0.1:12345", 12345),
        ("http://127.0.0.1:12345?x=1", 12345),
        ("http://user@127.0.0.1:12345", 12345),
        ("http://127.0.0.1:12345", 12346),
        ("http://127.0.0.1:12345", True),
        ("http://127.0.0.1:12345", None),
        (b"http://127.0.0.1:12345", 12345),
    ],
)
def test_browser_banner_refuses_noncanonical_or_unbound_opener(opener, port):
    with pytest.raises(ValueError):
        contract.browser_stdout(opener, port)


@pytest.mark.parametrize("mutation", [None, "missing", "extra", "wrong_port", "notice"])
def test_original_app_rows_bind_exact_browser_diagnostics(tmp_path, mutation):
    # Projected SOURCE parser inputs only, never a full installed proof.
    from tools.installed_native_menu import stream_record

    inputs = input_fixture()
    notice = b"SOURCE exact inert quit notice\n"
    controller_argv = ["python3", "-B", "/source/" + contract.SOURCE_FILE, "controller"]
    value = {
        "schema": contract.CONTROLLER,
        "uid": inputs["uid"],
        "gid": inputs["gid"],
        "pid": 10,
        "argv": controller_argv,
        "cmdline": contract.full_record(
            b"\0".join(p.encode() for p in controller_argv) + b"\0"
        ),
        "rows": [],
        "failure": None,
        "cleanup_errors": [],
        "acquisition_cleanup": [],
        "resources": {
            name: True
            for name in (
                "inner_thread_closed",
                "inner_requests_closed",
                "inner_socket_absent",
                "app_groups_absent",
            )
        },
        "cleanup_attempts": [
            {"resource": name, "succeeded": True}
            for name in (
                "app final reap",
                "relay shutdown",
                "relay close",
                "relay join",
                "relay socket removal",
                "controller final observation",
            )
        ],
    }
    for run in (1, 2):
        port = 12344 + run
        opener = f"http://127.0.0.1:{port}"
        stdout = f"Sinter local workspace: {opener}\n".encode()
        stderr = notice
        if run == 2:
            stdout = {
                "missing": b"",
                "extra": stdout + b"extra\n",
                "wrong_port": stdout.replace(b"12346", b"12347"),
            }.get(mutation, stdout)
            if mutation == "notice":
                stderr += b"extra\n"
        argv = [
            contract.BINARY,
            "app",
            "--mode",
            "browser",
            "--directory",
            "/proof/data",
        ]
        row = {
            "run": run,
            "pid": 10 + run,
            "argv": argv,
            "stop_method": "interface_quit",
            "forced_cleanup": False,
            "sigterm_sent": False,
            "cmdline": contract.full_record(
                b"\0".join(p.encode() for p in argv) + b"\0"
            ),
            "opener": contract.full_record(opener.encode()),
            "port": port,
            "exit_code": 0,
            "owned_group_remaining": False,
            "stdout": stream_record(io.BytesIO(stdout)),
            "stderr": stream_record(io.BytesIO(stderr)),
            "streams_complete": True,
            "port_closed": True,
            "returncode": 0,
            "cleanup_observation": {
                "errors": [],
                "attempts": [
                    {"resource": name, "succeeded": True}
                    for name in (
                        "app stop",
                        "stdout close",
                        "stderr close",
                        "stdout retention",
                        "stderr retention",
                        "listener observation",
                    )
                ],
            },
        }
        folder = tmp_path / "process" / f"run-{run}"
        folder.mkdir(parents=True)
        (folder / "stdout").write_bytes(stdout)
        (folder / "stderr").write_bytes(stderr)
        producer.write_json(folder / "observation.json", row)
        value["rows"].append(row)
    if mutation is None:
        assert contract.app_rows(value, inputs, notice, tmp_path) == (
            {11, 12},
            {12345, 12346},
        )
    else:
        with pytest.raises(ValueError, match="unexpected actual diagnostics"):
            contract.app_rows(value, inputs, notice, tmp_path)


def test_failed_host_cleanup_uses_fixed_early_path_and_keeps_original_failure(
    tmp_path, monkeypatch
):
    # Execute the real outer exception/cleanup code with inert transport only.
    from tools import installed_native_container as owner
    from tools import installed_native_menu as menu
    from tools import rc4_installed_recovery as recovery

    (tmp_path / "t").mkdir()
    inputs = input_fixture()
    args = SimpleNamespace(
        owner_sha256=inputs["owner_sha256"],
        source_commit=inputs["source_commit"],
        installer=Path(inputs["installer_name"]),
        package_receipt=Path(inputs["package_receipt_name"]),
    )
    monkeypatch.setattr(producer, "prepare", lambda _: (tmp_path, {}, {}, {}, inputs))
    monkeypatch.setattr(owner, "pins_for", lambda *_: {})
    sentinel = tmp_path / "inert-client"
    sentinel.write_bytes(b"SOURCE")
    monkeypatch.setattr(owner, "client_identity", lambda *_: {"path": str(sentinel)})
    monkeypatch.setattr(owner, "capture", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(contract, "outer_argv", lambda *_: ["SOURCE inert create"])
    monkeypatch.setattr(contract, "exec_argv", lambda *_: ["SOURCE inert controller"])
    monkeypatch.setattr(contract.recovery, "admitted_create", lambda *_: "1" * 64)
    monkeypatch.setattr(contract.native, "validate_image", lambda *_: None)
    monkeypatch.setattr(
        contract.native, "validate_container_observation", lambda *_: None
    )
    monkeypatch.setattr(contract.native, "validate_removal", lambda *_: None)
    monkeypatch.setattr(producer, "wait", lambda *_: None)
    monkeypatch.setattr(recovery, "browser_identity", lambda *_: inputs["browser"])
    monkeypatch.setattr(recovery, "source_records", lambda *_: inputs["qa_files"])

    def docker(role, argv, root, env, rows, clients, **kwargs):
        rows.append({"role": role})
        return (1 if role == "removed" else 0), b"[{}]"

    monkeypatch.setattr(owner, "docker_row", docker)

    class InertThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

        def join(self, **kwargs):
            pass

        def is_alive(self):
            return False

    monkeypatch.setattr(producer.threading, "Thread", InertThread)
    original = RuntimeError("SOURCE original controller refusal")
    actual_require = contract.require

    def require(condition, message):
        if not condition and message == "Actual user controller failed.":
            raise original
        actual_require(condition, message)

    monkeypatch.setattr(contract, "require", require)
    host = {
        "pid": 123,
        "exit_code": 1,
        "owned_group_remaining": False,
        "streams_complete": True,
        "passed": False,
        "stdout": menu.stream_record(io.BytesIO(b"")),
        "stderr": menu.stream_record(io.BytesIO(b"SOURCE failed collector\n")),
    }
    original_host = copy.deepcopy(host)

    def command(argv, rows, **kwargs):
        rows.append(host if "host" in argv else {"SOURCE": "controller refusal"})
        return 1, b""

    monkeypatch.setattr(menu, "command", command)
    with pytest.raises(RuntimeError) as raised:
        producer.run(args)
    assert raised.value is original and host == original_host
    retained = producer.read_json(tmp_path / "workflow-owner.json")
    assert retained["passed"] is False
    assert retained["failure"] == {"type": "RuntimeError", "message": str(original)}
    assert retained["host_command"] == original_host
    assert retained["browser"]["temporary_directory"] == str(tmp_path / "t")
    assert retained["browser"]["temporary_empty_before"] is True
    assert retained["browser"]["temporary_empty_after"] is True
    assert retained["browser"]["temporary_cleanup"]["complete"] is True
    assert retained["browser"]["temporary_cleanup"]["outcomes"] == []
    assert retained["cleanup_errors"] == [] and not any((tmp_path / "t").iterdir())
