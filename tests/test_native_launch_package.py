"""Native capability claims follow collected resources, not display availability."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import package_native as package


@pytest.fixture
def toolkit(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules, "_tkinter", SimpleNamespace(TCL_VERSION="8.6", TK_VERSION="8.6")
    )
    root = tmp_path / "origin"
    tcl, tk = root / "tcl8.6", root / "tk8.6"
    tcl.mkdir(parents=True)
    tk.mkdir()
    (tcl / "init.tcl").write_text("fictional Tcl bootstrap")
    (tk / "tk.tcl").write_text("fictional Tk bootstrap")
    libraries = [root / name for name in ("_tkinter.so", "libtcl.so", "libtk.so")]
    for library in libraries:
        library.write_bytes(b"fictional shared-library fixture")
    return SimpleNamespace(
        available=True,
        is_macos_system_framework=False,
        tkinter_extension_file=str(libraries[0]),
        tcl_shared_library=str(libraries[1]),
        tk_shared_library=str(libraries[2]),
        tcl_version=(8, 6),
        tk_version=(8, 6),
        tcl_data_dir=str(tcl),
        tk_data_dir=str(tk),
        data_files=[
            ("_tcl_data/init.tcl", str(tcl / "init.tcl"), "DATA"),
            ("_tk_data/tk.tcl", str(tk / "tk.tcl"), "DATA"),
        ],
    )


def test_default_freezer_preserves_cli_stdio_and_uses_standard_tk_hooks():
    arguments = package.freezer_arguments(False)
    assert "--console" in arguments
    assert "--windowed" not in arguments
    for name in ("tkinter", "_tkinter"):
        assert arguments[arguments.index(name) - 1] == "--hidden-import"
    assert arguments[arguments.index("sinter") - 1] == "--collect-submodules"


def test_explicit_compatibility_build_excludes_both_tk_modules():
    arguments = package.freezer_arguments(False, False)
    for name in ("tkinter", "_tkinter"):
        assert arguments[arguments.index(name) - 1] == "--exclude-module"
    assert "--console" in arguments


def test_matching_toolkit_preflight_does_not_open_a_display(toolkit):
    assert package.native_window_build_info(toolkit) is toolkit


@pytest.mark.parametrize(
    "field,value",
    [
        ("available", False),
        ("is_macos_system_framework", True),
        ("tcl_version", (9, 0)),
        ("tk_version", (9, 0)),
        ("tkinter_extension_file", None),
        ("tcl_shared_library", None),
        ("tk_shared_library", None),
        ("tcl_data_dir", None),
        ("tk_data_dir", None),
        ("data_files", []),
    ],
)
def test_missing_or_mismatched_dependency_refuses_before_build(toolkit, field, value):
    setattr(toolkit, field, value)
    with pytest.raises(RuntimeError, match="--without-native-window"):
        package.native_window_build_info(toolkit)


@pytest.mark.parametrize("entry", ["init.tcl", "tk.tcl"])
def test_incomplete_script_tree_refuses_before_build(toolkit, entry):
    directory = toolkit.tcl_data_dir if entry == "init.tcl" else toolkit.tk_data_dir
    (Path(directory) / entry).unlink()
    with pytest.raises(RuntimeError, match="script resources"):
        package.native_window_build_info(toolkit)


def test_missing_extension_import_has_actionable_compatibility_guidance(monkeypatch):
    monkeypatch.setitem(sys.modules, "_tkinter", None)
    with pytest.raises(RuntimeError, match="--without-native-window"):
        package.native_window_build_info()


@pytest.mark.parametrize("enabled", [False, True])
def test_frozen_window_receipt_records_resources_without_gui_qualification(enabled):
    package.verify_native_window_receipt(
        {"native_window_bundled": enabled, "native_display_tested": False}, enabled
    )


@pytest.mark.parametrize(
    "receipt",
    [
        {},
        {"native_window_bundled": False, "native_display_tested": False},
        {"native_window_bundled": True, "native_display_tested": True},
        {"native_window_bundled": True},
    ],
)
def test_missing_conflicting_or_overstated_window_receipt_refuses(receipt):
    with pytest.raises(RuntimeError):
        package.verify_native_window_receipt(receipt)


@pytest.mark.parametrize(
    "change",
    [{"native_window_bundled": False}, {"native_display_tested": True}],
)
def test_installed_capability_conflict_refuses_without_mutating_frozen_proof(change):
    receipt = {
        "schema": "sinter-native-test/v1",
        "version": package.__version__,
        "system": "Linux",
        "machine": "x86_64",
        "pointer_bits": 64,
        "python": "fixture",
        "passed": True,
        "frozen": True,
        "account_auth_bundled": False,
        "native_window_bundled": True,
        "native_display_tested": False,
    }
    original = copy.deepcopy(receipt)
    with pytest.raises(RuntimeError):
        package.record_installed_receipt(receipt, {**receipt, **change}, False, True)
    assert receipt == original


def test_installed_receipt_retains_native_resource_and_display_boundaries():
    receipt = {
        "schema": "sinter-native-test/v1",
        "version": package.__version__,
        "system": "Linux",
        "machine": "x86_64",
        "pointer_bits": 64,
        "python": "fixture",
        "passed": True,
        "frozen": True,
        "account_auth_bundled": False,
        "native_window_bundled": True,
        "native_display_tested": False,
    }
    installed = copy.deepcopy(receipt)
    package.record_installed_receipt(receipt, installed, False, True)
    for stage in ("frozen_test", "installed_test"):
        assert receipt[stage]["native_window_bundled"] is True
        assert receipt[stage]["native_display_tested"] is False


def test_windows_freezer_keeps_one_console_capable_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(package.sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(package, "run", lambda *args: calls.append(args))
    package.freeze_runtime(
        package.freezer_arguments(False),
        tmp_path,
        tmp_path / "sinter.ico",
        tmp_path / "sinter.icns",
    )
    assert len(calls) == 1
    assert "--console" in calls[0] and "--windowed" not in calls[0]
    assert calls[0][-1] == package.ROOT / "packaging/desktop_entry.py"


def test_macos_app_bundles_the_console_collection_without_a_second_backend(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(package.sys, "platform", "darwin")
    calls = []

    def run(*args):
        calls.append(args)
        if args[2] == "PyInstaller.utils.cliutils.makespec":
            (tmp_path / "Sinter.spec").write_text(
                "exe = EXE(console=True)\ncoll = COLLECT(exe)\n"
            )

    monkeypatch.setattr(package, "run", run)
    package.freeze_runtime(
        package.freezer_arguments(False),
        tmp_path,
        tmp_path / "sinter.ico",
        tmp_path / "sinter.icns",
    )
    assert len(calls) == 2
    spec = (tmp_path / "Sinter.spec").read_text()
    assert "console=True" in spec
    assert "BUNDLE(coll, name='Sinter.app'" in spec
    assert "io.neuroforge.sinter" in spec
    assert "info_plist={'LSBackgroundOnly': False}" in spec
    assert "--windowed" not in calls[0]
    assert "--console" in calls[0]
    assert calls[1][-1] == tmp_path / "Sinter.spec"


@pytest.fixture
def script_bundle(toolkit, tmp_path, monkeypatch):
    monkeypatch.setattr(package.sys, "platform", "linux")
    runtime, notices = tmp_path / "runtime", tmp_path / "notices"
    notices.mkdir()
    for target, origin, _ in toolkit.data_files:
        destination = runtime / "_internal" / target
        destination.parent.mkdir(parents=True)
        destination.write_bytes(Path(origin).read_bytes())
    documentation = tmp_path / "doc"
    for name in ("tcl-fixture", "tk-fixture"):
        folder = documentation / name
        folder.mkdir(parents=True)
        (folder / "copyright").write_text(f"Original {name} copyright.\n")
    monkeypatch.setattr(
        package,
        "package_owner",
        lambda path: (
            "tcl-fixture" if path.name == "init.tcl" else "tk-fixture",
            "1.0",
        ),
    )
    return toolkit, runtime, notices, documentation


def test_all_bundled_tcl_tk_scripts_keep_exact_origin_hash_and_notices(script_bundle):
    toolkit, runtime, notices, documentation = script_bundle
    rows = package.collect_toolkit_licences(
        toolkit, notices, runtime, documentation=documentation
    )
    assert {row["name"] for row in rows} == {"Tcl", "Tk"}
    assert sum(len(row["scripts"]) for row in rows) == 2
    for row in rows:
        assert row["purpose"] == "bundled_native_toolkit"
        for item in row["scripts"]:
            assert package.digest(runtime / item["path"]) == item["sha256"]
            assert package.digest(Path(item["origin"])) == item["sha256"]
        for item in row["licences"]:
            assert package.digest(notices / item["path"]) == item["sha256"]


@pytest.mark.parametrize(
    "mutation",
    ["missing_script", "changed_script", "missing_notice", "duplicate", "unsafe"],
)
def test_lost_script_origin_or_original_notice_refuses_package(script_bundle, mutation):
    toolkit, runtime, notices, documentation = script_bundle
    toolkit = copy.deepcopy(toolkit)
    bundled = runtime / "_internal/_tk_data/tk.tcl"
    if mutation == "missing_script":
        bundled.unlink()
    elif mutation == "changed_script":
        bundled.write_text("unrelated script")
    elif mutation == "missing_notice":
        (documentation / "tk-fixture/copyright").unlink()
    elif mutation == "duplicate":
        toolkit.data_files.append(toolkit.data_files[-1])
    else:
        toolkit.data_files[-1] = (
            "_tk_data/../../outside",
            toolkit.data_files[-1][1],
            "DATA",
        )
    with pytest.raises((RuntimeError, FileNotFoundError)):
        package.collect_toolkit_licences(
            toolkit, notices, runtime, documentation=documentation
        )


def test_python_licence_is_not_substituted_for_toolkit_notices(
    script_bundle, monkeypatch
):
    toolkit, runtime, notices, _ = script_bundle
    monkeypatch.setattr(package.sys, "platform", "win32")
    (Path(toolkit.tcl_data_dir).parent.parent / "LICENSE").write_text(
        "Python only licence"
    )
    with pytest.raises(RuntimeError, match="Tcl original runtime licence"):
        package.collect_toolkit_licences(toolkit, notices, runtime)
