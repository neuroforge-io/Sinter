"""Fictional files and inert owners only; no external tool or app is launched."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_rc4_native_handoff import browser_fixture
from tests.test_rc4_native_handoff import synthetic as synthetic
from tools import rc4_host_tools as host
from tools import rc4_native_handoff as handoff
from tools import rc4_native_handoff_contract as native_contract
from tools import rc4_replacement as replacement
from tools import rc4_replacement_contract as contract
from tools import rc4_replacement_probe as probe


@pytest.fixture
def selected(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip(
            "This physical source control requires the Linux/POSIX host-path profile; pure snapshot parsers remain active."
        )
    import importlib.metadata
    import shutil

    library = tmp_path / "playwright"
    (library / "driver/package").mkdir(parents=True)
    files = {
        "chromium": tmp_path / "chromium",
        "docker": tmp_path / "docker",
        "python": tmp_path / "python",
        "node": library / "driver/node",
        "cli": library / "driver/package/cli.js",
        "library": library / "__init__.py",
    }
    for role, path in files.items():
        path.write_bytes(("fictional actual file " + role).encode())
    module = SimpleNamespace(__file__=str(files["library"]))
    monkeypatch.setitem(sys.modules, "playwright", module)
    monkeypatch.setattr(sys, "executable", str(files["python"]))
    monkeypatch.setattr(shutil, "which", lambda name, path: str(files["docker"]))
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "1.58.0")
    return files, tmp_path / "t"


@pytest.fixture
def closed_pair():
    def file(role):
        return {
            "path": "/owned/external/" + role,
            "bytes": 123,
            "sha256": hashlib.sha256(role.encode()).hexdigest(),
        }

    before = {
        "tools": {role: file(role) for role in host.TOOLS},
        "browser_tmp": "/owned/browser-temp",
        "python_launch": "/owned/external/python",
        "playwright_version": "1.58.0",
        "driver_cli": file("cli.js"),
        "collector_source": file("collector.py"),
    }
    return {
        "schema": "sinter-rc4-host-tools/v1",
        "boundary": host.BOUNDARY,
        "before": before,
        "after": copy.deepcopy(before),
        "after_errors": [],
    }


def pair(selected):
    files, temporary = selected
    before = contract.host_identity(files["chromium"], temporary)
    after, errors, primary = contract.observe_host_identity(
        files["chromium"], temporary
    )
    assert errors == [] and primary is None
    return {
        "schema": "sinter-rc4-host-tools/v1",
        "boundary": host.BOUNDARY,
        "before": before,
        "after": after,
        "after_errors": errors,
    }


def test_independent_reads_of_complete_fictional_host_files_keep_payloads_external(
    selected,
):
    files, _ = selected
    value = pair(selected)
    host.validate_host_pair(value)
    assert value["before"] is not value["after"]
    for role, file_role in (
        ("docker", "docker"),
        ("chromium", "chromium"),
        ("python", "python"),
        ("playwright_node", "node"),
    ):
        record = value["before"]["tools"][role]
        assert record == {
            "path": str(files[file_role]),
            "bytes": files[file_role].stat().st_size,
            "sha256": hashlib.sha256(files[file_role].read_bytes()).hexdigest(),
        }
        assert set(record) == {"path", "bytes", "sha256"}


@pytest.mark.parametrize(
    "role",
    [
        "docker",
        "chromium",
        "python",
        "playwright_node",
        "driver_cli",
        "collector_source",
    ],
)
@pytest.mark.parametrize(
    "attack",
    [
        "missing_after",
        "null_after",
        "changed_hash",
        "changed_bytes",
        "changed_path",
        "boolean_bytes",
        "extra_field",
    ],
)
def test_host_pair_refuses_missing_changed_or_untyped_observed_after(
    closed_pair, role, attack
):
    value = copy.deepcopy(closed_pair)
    target = value["after"]["tools"] if role in host.TOOLS else value["after"]
    record = target[role]
    if attack == "missing_after":
        del target[role]
    elif attack == "null_after":
        target[role] = None
    elif attack == "changed_hash":
        record["sha256"] = "f" * 64
    elif attack == "changed_bytes":
        record["bytes"] += 1
    elif attack == "changed_path":
        record["path"] += "-different"
    elif attack == "boolean_bytes":
        record["bytes"] = True
    else:
        record["passed"] = True
    with pytest.raises(ValueError):
        host.validate_host_pair(value)


@pytest.mark.parametrize(
    "attack",
    [
        "old_snapshot",
        "old_schema",
        "errors",
        "no_after",
        "after_boolean",
        "metadata_changed",
        "metadata_untyped",
        "node_omitted",
        "daemon_claim",
    ],
)
def test_closed_host_pair_does_not_promote_old_metadata_or_booleans(
    closed_pair, attack
):
    value = copy.deepcopy(closed_pair)
    if attack == "old_snapshot":
        value = value["before"]
    elif attack == "old_schema":
        value["schema"] = "sinter-rc4-host-tools/v0"
    elif attack == "errors":
        value["after_errors"] = [{"role": "node", "error": "actual failed read"}]
    elif attack == "no_after":
        del value["after"]
    elif attack == "after_boolean":
        value["after"] = True
    elif attack == "metadata_changed":
        value["after"]["playwright_version"] = "1.59.0"
    elif attack == "metadata_untyped":
        value["after"]["python_launch"] = True
    elif attack == "node_omitted":
        del value["before"]["tools"]["playwright_node"]
    else:
        value["boundary"] = "fully attested Docker daemon"
    with pytest.raises(ValueError):
        host.validate_host_pair(value)


@pytest.mark.parametrize("role", ["docker", "chromium", "python", "node", "cli"])
def test_real_fictional_file_change_is_independently_observed_and_refused(
    selected, role
):
    files, temporary = selected
    before = contract.host_identity(files["chromium"], temporary)
    files[role].write_bytes(files[role].read_bytes() + b" actual changed bytes")
    after, errors, primary = contract.observe_host_identity(
        files["chromium"], temporary
    )
    assert errors == [] and primary is None
    with pytest.raises(ValueError, match="changed"):
        host.validate_host_pair(
            {
                "schema": "sinter-rc4-host-tools/v1",
                "boundary": host.BOUNDARY,
                "before": before,
                "after": after,
                "after_errors": [],
            }
        )


def test_after_failure_does_not_skip_any_other_actual_host_read(selected, monkeypatch):
    files, temporary = selected
    before = contract.host_identity(files["chromium"], temporary)
    files["chromium"].unlink()
    files["node"].unlink()
    seen, original = [], host.fingerprint

    def read(path):
        seen.append(str(path))
        return original(path)

    monkeypatch.setattr(host, "fingerprint", read)
    after, errors, primary = contract.observe_host_identity(
        files["chromium"], temporary
    )
    assert isinstance(primary, FileNotFoundError)
    assert [row["role"] for row in errors] == ["chromium", "playwright_node"]
    assert len(seen) == 6
    assert after["tools"]["docker"] == before["tools"]["docker"]
    assert after["tools"]["python"] == before["tools"]["python"]
    assert after["driver_cli"] == before["driver_cli"]
    assert after["collector_source"] == before["collector_source"]


@pytest.mark.parametrize("body_failed", [False, True])
@pytest.mark.parametrize("publish_failed", [False, True])
def test_actual_after_read_failure_preserves_first_and_attempts_both_publications(
    selected, monkeypatch, body_failed, publish_failed
):
    files, temporary = selected
    value = pair(selected)
    value["after"] = None
    bundle = {
        "schema": "sinter-rc4-replacement-owner/v2",
        "host": value,
        "cleanup_failure": None,
    }
    folder = files["chromium"].parent
    files["chromium"].unlink()
    primary = RuntimeError("ORIGINAL-INSTALLED-OWNER") if body_failed else None
    attempted, writer = [], probe.write

    def publish(path, record):
        attempted.append(path.name)
        if publish_failed:
            raise OSError("LATER-PUBLICATION-" + path.name)
        writer(path, record)

    monkeypatch.setattr(probe, "write", publish)
    with pytest.raises(probe.EvidenceFailure) as result:
        replacement.retain_host_after(
            bundle, folder, files["chromium"], temporary, primary
        )
    assert attempted == ["outer.json", "outer-host-failed.json"]
    error = result.value
    assert error.__cause__ is error.primary_exception
    if body_failed:
        assert error.primary_exception is primary
    else:
        assert isinstance(error.primary_exception, FileNotFoundError)
    assert "chromium" in " ".join(error.cleanup_errors)
    assert bundle["host"]["after"]["tools"]["chromium"] is None
    assert bundle["host"]["after"]["tools"]["playwright_node"] is not None
    assert bool(error.unpublished_bytes) == publish_failed
    if publish_failed:
        raw = error.unpublished_bytes[str(folder / "outer.json")]
        assert json.loads(raw)["host"]["after_errors"][0]["role"] == "chromium"
        assert set(error.unpublished_bytes) == {
            str(folder / "outer.json"),
            str(folder / "outer-host-failed.json"),
        }


def test_successful_after_retention_uses_second_read_instead_of_before_alias(selected):
    files, temporary = selected
    value = pair(selected)
    value["after"] = None
    bundle = {
        "schema": "sinter-rc4-replacement-owner/v2",
        "host": value,
        "cleanup_failure": None,
    }
    replacement.retain_host_after(
        bundle, files["chromium"].parent, files["chromium"], temporary, None
    )
    host.validate_host_pair(bundle["host"])
    retained = json.loads((files["chromium"].parent / "outer.json").read_bytes())
    assert retained["host"]["after"] == value["before"]
    assert value["after"] is not value["before"]


@pytest.mark.parametrize("role", ["chromium", "driver_process"])
@pytest.mark.parametrize(
    "attack", ["missing", "null", "changed", "boolean", "old_schema"]
)
def test_native_browser_requires_observed_after_for_actual_selected_binaries(
    synthetic, role, attack
):
    inner, _, _ = synthetic
    value = browser_fixture(inner)
    if attack == "old_schema":
        value["schema"] = "sinter-rc4-native-handoff-browser/v1"
    elif attack == "missing":
        del value[role]["sha256_after"]
    else:
        value[role]["sha256_after"] = {
            "null": None,
            "changed": "f" * 64,
            "boolean": True,
        }[attack]
    with pytest.raises((ValueError, KeyError)):
        native_contract.validate_browser(value, inner)


@pytest.mark.parametrize("body_failed", [False, True])
@pytest.mark.parametrize("read_failed", [False, True])
@pytest.mark.parametrize("writer_failed", [False, True])
def test_native_actual_docker_after_and_retention_preserve_first_and_all_attempts(
    tmp_path, monkeypatch, body_failed, read_failed, writer_failed
):
    seen = []
    first = RuntimeError("FIRST-NATIVE-HANDOFF")
    read_error = OSError("LATER-ACTUAL-DOCKER-READ")
    write_error = OSError("LATER-SIDECAR-PUBLICATION")

    def lifecycle(*_):
        seen.append("lifecycle")
        if body_failed:
            raise first
        return "c" * 64

    def digest(path):
        seen.append("actual-after-read")
        assert path == Path(client["path"])
        if read_failed:
            raise read_error
        return "a" * 64

    def write(path, value):
        seen.append(path.name)
        if writer_failed and path.name == "client-commands.json":
            raise write_error
        path.write_text(json.dumps(value))

    monkeypatch.setattr(handoff, "handoff_lifecycle", lifecycle)
    monkeypatch.setattr(handoff.native, "binary_digest", digest)
    monkeypatch.setattr(handoff, "write_json", write)
    client = {"path": "/fixed/docker", "sha256": "a" * 64}
    records = {name: {"sha256": "b" * 64, "bytes": 1} for name in native_contract.FILES}
    args = (
        tmp_path,
        {},
        {},
        [],
        [],
        [],
        native_contract.HOST_CHROMIUM,
        client,
        records,
    )
    if body_failed or read_failed or writer_failed:
        with pytest.raises((RuntimeError, OSError)) as result:
            handoff.observe_handoff_outer(*args)
        expected = first if body_failed else read_error if read_failed else write_error
        assert result.value is expected
        assert len(result.value.host_observation_errors) == int(read_failed) + int(
            writer_failed
        )
    else:
        assert handoff.observe_handoff_outer(*args) == "c" * 64
    assert seen == [
        "lifecycle",
        "actual-after-read",
        "client-commands.json",
        "outer.json",
    ]
    raw = json.loads((tmp_path / "outer.json").read_bytes())
    assert raw["docker_client"]["sha256_after"] == (None if read_failed else "a" * 64)


@pytest.mark.parametrize("role", ["first", "second", "both"])
def test_independent_observation_errors_keep_original_exception_and_all_reads(role):
    first, second = OSError("FIRST"), RuntimeError("SECOND")
    seen = []

    def read(name, error):
        seen.append(name)
        if role in {name, "both"}:
            raise error
        return name

    records, errors, primary = host.observe(
        {
            "first": lambda: read("first", first),
            "second": lambda: read("second", second),
            "last": lambda: seen.append("last") or "original",
        }
    )
    assert seen == ["first", "second", "last"]
    assert primary is (second if role == "second" else first)
    assert records["last"] == "original"
    assert len(errors) == (2 if role == "both" else 1)


def test_collector_and_docker_child_environment_selects_bundled_node_and_path(
    selected, monkeypatch
):
    files, temporary = selected
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", "/unapproved/other-node")
    monkeypatch.setenv("API_SECRET", "not transmitted")
    seen = []

    def popen(argv, **kwargs):
        seen.append((argv, kwargs["env"]))
        return SimpleNamespace(pid=1123, wait=lambda **_: 0)

    monkeypatch.setattr(replacement.subprocess, "Popen", popen)
    argv = contract.collector_argv(
        files["chromium"].parent, files["chromium"], "prior", temporary
    )
    replacement.command(
        argv, [], "mapped-collector", files["chromium"].parent / "streams"
    )
    replacement.command(
        ["docker", "image", "inspect", "sha256:" + "a" * 64],
        [],
        "mapped-docker",
        files["chromium"].parent / "streams",
    )
    assert len(seen) == 2
    for _, environment in seen:
        assert environment["PATH"] == os.defpath
        assert (
            "PLAYWRIGHT_NODEJS_PATH" not in environment
            and "API_SECRET" not in environment
        )
    assert contract.host_identity(files["chromium"], temporary)["tools"][
        "playwright_node"
    ]["path"] == str(files["node"])


@pytest.mark.parametrize(
    "attack", ["empty", "directory", "symlink", "relative", "oversize"]
)
def test_fingerprint_refuses_noncanonical_external_files(tmp_path, monkeypatch, attack):
    path = tmp_path / "external"
    if attack == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"" if attack == "empty" else b"original file")
    if attack == "symlink":
        link = tmp_path / "link"
        try:
            link.symlink_to(path)
        except OSError:
            pytest.skip("Symlink capability unavailable for this one physical control.")
        path = link
    elif attack == "relative":
        path = Path("external")
    elif attack == "oversize":
        monkeypatch.setattr(host, "MAX_HOST_FILE", 1)
    with pytest.raises((ValueError, OSError)):
        host.fingerprint(path)


@pytest.mark.parametrize("failed_after", [None, "chromium", "node", "both"])
def test_native_browser_reads_both_actual_after_files_even_with_primary_failure(
    tmp_path, monkeypatch, failed_after
):
    """Controlled native browser owner; no browser, Node, thread or app starts."""
    root = tmp_path / "owner/out/handoff"
    root.mkdir(parents=True)
    (root.parent.parent / "client").mkdir()
    first = RuntimeError("ORIGINAL-VISIBLE-UI")
    driver = Path("/fixed/playwright/driver/node").resolve()
    reads, seen = [], []

    def digest(path):
        role = "chromium" if path == native_contract.HOST_CHROMIUM else "node"
        reads.append(role)
        if len(reads) > 2 and failed_after in {role, "both"}:
            raise OSError("AFTER-" + role)
        return ("a" if len(reads) <= 2 else "b") * 64

    relay = SimpleNamespace(
        server_address=("127.0.0.1", 32124),
        model_requests=0,
        errors=0,
        serve_forever=lambda: None,
        idle=lambda: True,
        shutdown=lambda: seen.append("relay-shutdown"),
        server_close=lambda: seen.append("relay-close"),
    )
    thread = SimpleNamespace(
        start=lambda: None,
        join=lambda **_: seen.append("thread-join"),
        is_alive=lambda: False,
    )
    page = SimpleNamespace(
        on=lambda *_: None, goto=lambda *_: (_ for _ in ()).throw(first)
    )
    context = SimpleNamespace(
        route_web_socket=lambda *_: None,
        route=lambda *_: None,
        new_page=lambda: page,
        close=lambda: seen.append("context-close"),
    )
    chrome = SimpleNamespace(
        new_browser_cdp_session=lambda: SimpleNamespace(
            send=lambda *_: {"processInfo": [{"id": 901}, {"id": 902}]}
        ),
        version="inert-fixture",
        new_context=lambda: context,
        close=lambda: seen.append("browser-close"),
    )
    engine = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=lambda *_: chrome),
        stop=lambda: seen.append("driver-stop"),
    )
    monkeypatch.setitem(
        sys.modules,
        "playwright",
        SimpleNamespace(__file__="/fixed/playwright/__init__.py"),
    )
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        SimpleNamespace(
            expect=lambda *_: None,
            sync_playwright=lambda: SimpleNamespace(start=lambda: engine),
        ),
    )
    child_calls = iter([set(), {903}])
    monkeypatch.setattr(handoff, "children", lambda: next(child_calls))
    monkeypatch.setattr(handoff, "wait_file", lambda *_: {})
    monkeypatch.setattr(handoff.transport, "Relay", lambda *_: relay)
    monkeypatch.setattr(handoff.threading, "Thread", lambda **_: thread)
    monkeypatch.setattr(handoff.native, "binary_digest", digest)
    monkeypatch.setattr(handoff.os, "readlink", lambda *_: str(driver))
    monkeypatch.setattr(handoff, "alive", lambda *_: False)
    monkeypatch.setattr(handoff, "port_closed", lambda *_: True)

    def popen(*_args, **_kwargs):
        profile = root.parent.parent / "client/browser-home/profile"
        profile.mkdir()
        (profile / "DevToolsActivePort").write_text(
            "32125\n/devtools/browser/a-b-c\n", encoding="ascii"
        )
        return SimpleNamespace(pid=901, poll=lambda: 0)

    monkeypatch.setattr(handoff.subprocess, "Popen", popen)
    monkeypatch.setattr(
        handoff.native,
        "stop_process",
        lambda _process, row: row.update(
            exit_code=0, sigterm_sent=False, owned_group_remaining=False
        ),
    )
    # Popen must report live while the debugger is being discovered, then reaped.
    polls = iter([None, 0, 0])
    original_popen = handoff.subprocess.Popen

    def launch(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        process.poll = lambda: next(polls, 0)
        return process

    monkeypatch.setattr(handoff.subprocess, "Popen", launch)
    with pytest.raises(RuntimeError) as result:
        handoff.browser(root, native_contract.HOST_CHROMIUM)
    assert result.value is first
    assert reads == ["chromium", "node", "chromium", "node"]
    retained = json.loads((root.parent.parent / "browser.json").read_bytes())
    assert retained["schema"] == "sinter-rc4-native-handoff-browser/v2"
    for key, role in (("chromium", "chromium"), ("driver_process", "node")):
        assert retained[key]["sha256"] == "a" * 64
        assert retained[key]["sha256_after"] == (
            None if failed_after in {role, "both"} else "b" * 64
        )
    assert "context-close" in seen and "browser-close" in seen and "driver-stop" in seen
    assert "relay-shutdown" in seen and "relay-close" in seen and "thread-join" in seen
    assert len(retained.get("cleanup_errors", [])) == (
        2 if failed_after == "both" else int(failed_after is not None)
    )


@pytest.mark.parametrize("read_failed", [False, True])
def test_external_file_close_fault_retains_first_read_failure_and_later_attempts(
    tmp_path, monkeypatch, read_failed
):
    path = tmp_path / "host-tool"
    path.write_bytes(b"original host tool bytes")
    first = OSError("FIRST-ACTUAL-FILE-READ")
    close_error = OSError("LATER-OWNED-FILE-CLOSE")
    original_open, seen = Path.open, []

    def open_file(value, *args, **kwargs):
        actual = original_open(value, *args, **kwargs)
        if value != path:
            return actual

        def read(size):
            seen.append("read")
            if read_failed:
                raise first
            return actual.read(size)

        def close():
            seen.append("close")
            actual.close()
            raise close_error

        return SimpleNamespace(fileno=actual.fileno, read=read, close=close)

    monkeypatch.setattr(Path, "open", open_file)
    records, errors, primary = host.observe(
        {
            "host-file": lambda: host.fingerprint(path),
            "last": lambda: seen.append("last") or "actual later result",
        }
    )
    assert primary is (first if read_failed else close_error)
    assert seen[-2:] == ["close", "last"]
    assert records["last"] == "actual later result"
    assert [row["role"] for row in errors] == (
        ["host-file", "host-file.close"] if read_failed else ["host-file"]
    )
    assert any("LATER-OWNED-FILE-CLOSE" in row["error"] for row in errors)


def test_actual_host_gate_refuses_missing_optional_library_without_fabricated_reads(
    tmp_path,
    monkeypatch,
):
    import builtins
    import shutil

    fake_docker = tmp_path / "configured-docker"
    fake_docker.write_bytes(b"fictional Docker file; never executed")
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: str(fake_docker))

    original_import, seen = builtins.__import__, []

    def missing(name, *args, **kwargs):
        if name == "playwright":
            raise ModuleNotFoundError("Actual optional Playwright library unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    monkeypatch.setattr(host, "fingerprint", lambda path: seen.append(str(path)))
    with pytest.raises(ModuleNotFoundError, match="Playwright"):
        contract.host_identity(Path("/owned/selected-chromium"), Path("/owned/t"))
    assert len(seen) == 4
    assert not any(path.endswith("/node") or path.endswith("/cli.js") for path in seen)


def test_redirected_after_chromium_keeps_all_other_discovery_and_reads(
    selected, monkeypatch
):
    files, temporary = selected
    before = contract.host_identity(files["chromium"], temporary)
    files["chromium"].unlink()
    try:
        files["chromium"].symlink_to(files["docker"])
    except OSError:
        pytest.skip("Symlink capability unavailable for this one physical control.")
    seen, original = [], host.fingerprint

    def read(path):
        seen.append(str(path))
        return original(path)

    monkeypatch.setattr(host, "fingerprint", read)
    after, errors, primary = contract.observe_host_identity(
        files["chromium"], temporary
    )
    assert isinstance(primary, ValueError)
    assert [row["role"] for row in errors] == ["chromium"]
    assert len(seen) == 6
    for role in ("docker", "python", "playwright_node"):
        assert after["tools"][role] == before["tools"][role]
