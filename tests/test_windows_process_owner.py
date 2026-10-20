"""Actual finite Windows ownership controls, separate from launcher readiness."""

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import windows_process_owner as owner

WINDOWS = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("SINTER_WINDOWS_OWNER_CONTROLS") != "1",
    reason="Actual Windows ownership controls require the dedicated fail-fast workflow.",
)


def _receipt(process, directory, label):
    value = process.finish()
    destination = os.environ.get("SINTER_STARTUP_DIAGNOSTICS_DIR")
    if destination:
        output = Path(destination).resolve()
        output.mkdir(parents=True, exist_ok=True)
        # Each test has an independent fixture and a fixed, non-private label.
        (output / (label + ".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")
    assert value["clean"], value
    assert value["active_after"] == 0 and value["parent_reaped"], value
    assert value["startup_handles_closed"]
    assert value["job_handle_closed"] and value["process_handle_closed"]
    return value


def _launch(tmp_path, code, *, arguments=(), **kwargs):
    stdout, stderr = (tmp_path / name for name in ("stdout.bin", "stderr.bin"))
    with stdout.open("wb") as out, stderr.open("wb") as err:
        return owner.WindowsOwnedProcess(
            [sys.executable, "-I", "-S", "-B", "-c", code, *arguments],
            cwd=tmp_path, stdout=out, stderr=err, **kwargs,
        )


def _wait_for(path, timeout=5):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("The fictional child did not write its marker.")
        time.sleep(0.01)


@pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows refusal control.")
def test_other_platform_refuses_before_launching_or_creating_outputs(tmp_path):
    with pytest.raises(OSError, match="requires Windows"):
        owner.WindowsOwnedProcess(
            [sys.executable, "-c", "raise AssertionError('must not run')"],
            cwd=tmp_path, stdout=None, stderr=None,
        )
    assert list(tmp_path.iterdir()) == []


@WINDOWS
def test_native_structure_sizes_match_supported_windows_abi():
    pointer = ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(owner._StartupInfo) == (104 if pointer == 8 else 68)
    assert ctypes.sizeof(owner._StartupInfoEx) == (112 if pointer == 8 else 72)
    assert ctypes.sizeof(owner._ExtendedLimits) == (144 if pointer == 8 else 112)
    assert ctypes.sizeof(owner._Accounting) == 48


@WINDOWS
def test_ordinary_arguments_environment_streams_flags_and_exit_survive(tmp_path, monkeypatch):
    monkeypatch.setenv("SINTER_OWNER_FICTIONAL", "retained")
    arguments = ["space value", "Ω café", "%fictional%", "! & (literal)"]
    code = (
        "import json,os,sys\n"
        "assert sys.stdin.buffer.read(1) == b''\n"
        "print(json.dumps({'args':sys.argv[1:], 'cwd':os.getcwd(), "
        "'no_site':sys.flags.no_site, 'isolated':sys.flags.isolated, "
        "'environment':os.environ.get('SINTER_OWNER_FICTIONAL')}), flush=True)\n"
        "os.write(2,b'fictional stderr\\xff')\n"
        "raise SystemExit(7)\n"
    )
    process = _launch(tmp_path, code, arguments=arguments)
    try:
        assert process.wait(timeout=5) == 7
    finally:
        proof = _receipt(process, tmp_path, "ordinary")
    value = json.loads((tmp_path / "stdout.bin").read_text())
    assert value == {
        "args": arguments, "cwd": str(tmp_path),
        "no_site": 1, "isolated": 1, "environment": "retained",
    }
    assert (tmp_path / "stderr.bin").read_bytes() == b"fictional stderr\xff"
    assert proof["identity"]["atomic_job_assignment"]
    assert proof["identity"]["membership_verified_before_resume"]
    assert Path(proof["identity"]["image"]).samefile(sys.executable)
    assert proof["identity"]["creation_filetime"] > 0


@WINDOWS
def test_parent_exit_does_not_leave_a_child_or_grandchild_writing(tmp_path):
    ready = tmp_path / "grandchild-ready"
    grandchild = (
        "import os,time\n"
        f"open({str(ready)!r},'w').write('ready')\n"
        "os.write(1,b'grandchild ready\\n')\n"
        "time.sleep(30)\n"
        "os.write(1,b'must not be written\\n')\n"
    )
    child = (
        "import subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable,'-I','-S','-B','-c',{grandchild!r}],stdin=subprocess.DEVNULL,stdout=sys.stdout,stderr=sys.stderr)\n"
        "time.sleep(30)\n"
    )
    parent = (
        "import pathlib,subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable,'-I','-S','-B','-c',{child!r}],stdin=subprocess.DEVNULL,stdout=sys.stdout,stderr=sys.stderr)\n"
        f"ready=pathlib.Path({str(ready)!r});deadline=time.monotonic()+5\n"
        "while not ready.exists() and time.monotonic()<deadline:time.sleep(0.01)\n"
        "assert ready.exists()\n"
        "print('parent finished',flush=True)\n"
    )
    process = _launch(tmp_path, parent)
    try:
        assert process.wait(timeout=5) == 0
        assert process.active_processes() >= 2
    finally:
        proof = _receipt(process, tmp_path, "early-parent-exit")
    assert proof["active_before"] >= 2
    raw = (tmp_path / "stdout.bin").read_bytes()
    assert b"grandchild ready" in raw and b"parent finished" in raw
    assert b"must not be written" not in raw


@WINDOWS
def test_timeout_reaps_the_owned_tree_with_one_cleanup_deadline(tmp_path):
    process = _launch(tmp_path, "import time;time.sleep(30)")
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.05)
    finally:
        proof = _receipt(process, tmp_path, "timeout")
    assert process.returncode != 0
    assert proof["active_before"] >= 1


@WINDOWS
def test_keyboard_interrupt_keeps_the_original_fault_and_cleans_tree(tmp_path):
    process = _launch(tmp_path, "import time;time.sleep(30)")
    original = KeyboardInterrupt("fictional operator interrupt")
    with pytest.raises(KeyboardInterrupt) as caught:
        with process:
            raise original
    assert caught.value is original
    _receipt(process, tmp_path, "keyboard-interrupt")


@WINDOWS
@pytest.mark.parametrize("fault", [
    "job-attribute", "membership", "resume", "duplicate-after-native", "create-after-native",
])
def test_setup_refusal_never_executes_the_child_and_keeps_first_fault(
    tmp_path, monkeypatch, fault
):
    marker = tmp_path / "must-not-run"
    original = (KeyboardInterrupt if fault.endswith("-after-native") else OSError)(
        "controlled " + fault
    )
    returned_handles = []
    if fault in ("duplicate-after-native", "create-after-native"):
        api = owner._WinAPI()
        method = "duplicate" if fault.startswith("duplicate") else "create"
        native = getattr(api, method)

        def interrupt_after_native(*args):
            owner._check(native(*args))
            if method == "create":
                value = ctypes.cast(args[-1], ctypes.POINTER(owner._ProcessInfo)).contents
                returned_handles.extend([value.process, value.thread])
            else:
                value = ctypes.cast(args[3], ctypes.POINTER(owner.wintypes.HANDLE)).contents
                returned_handles.append(value.value)
            raise original

        monkeypatch.setattr(api, method, interrupt_after_native)
        options = {"_api": api}
    elif fault == "job-attribute":
        api = owner._WinAPI()
        update = api.update

        def refuse(attributes, flags, key, *rest):
            if key == 0x2000D:
                raise original
            return update(attributes, flags, key, *rest)

        monkeypatch.setattr(api, "update", refuse)
        options = {"_api": api}
    else:
        method = "_verify_membership" if fault == "membership" else "_resume"

        def refuse(*args):
            raise original

        monkeypatch.setattr(owner.WindowsOwnedProcess, method, refuse)
        options = {}
    with pytest.raises(type(original)) as caught:
        _launch(tmp_path, f"open({str(marker)!r},'w').write('unexpected')", **options)
    assert caught.value is original
    proof = caught.value.owned_tree
    assert proof["clean"] and proof["active_after"] == 0, proof
    assert proof["parent_reaped"] and proof["startup_handles_closed"]
    assert proof["resumed"] is False
    assert proof["process_created"] is (fault not in ("job-attribute", "duplicate-after-native"))
    assert not marker.exists()
    info = ctypes.WinDLL("kernel32", use_last_error=True).GetHandleInformation
    info.argtypes = [owner.wintypes.HANDLE, ctypes.POINTER(owner.wintypes.DWORD)]
    info.restype = owner.wintypes.BOOL
    for handle in returned_handles:
        flags = owner.wintypes.DWORD()
        ctypes.set_last_error(0)
        assert not info(handle, ctypes.byref(flags))
        assert ctypes.get_last_error() == 6  # ERROR_INVALID_HANDLE, before any new launch.
    destination = os.environ.get("SINTER_STARTUP_DIAGNOSTICS_DIR")
    if destination:
        (Path(destination) / ("setup-" + fault + ".json")).write_text(
            json.dumps(proof, indent=2), encoding="utf-8",
        )


@WINDOWS
def test_unrelated_inheritable_handle_is_excluded(tmp_path):
    import msvcrt

    sentinel = tmp_path / "private-sentinel"
    with sentinel.open("w+b") as stream:
        os.set_inheritable(stream.fileno(), True)
        handle = msvcrt.get_osfhandle(stream.fileno())
        code = (
            "import ctypes,json,sys\n"
            "from ctypes import wintypes\n"
            "f=ctypes.WinDLL('kernel32',use_last_error=True).GetFinalPathNameByHandleW\n"
            "f.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]\n"
            "f.restype=wintypes.DWORD\n"
            "text=ctypes.create_unicode_buffer(32768)\n"
            f"size=f({handle},text,32768,0)\n"
            "print(json.dumps(text.value if size else None),flush=True)\n"
        )
        process = _launch(tmp_path, code)
        try:
            assert process.wait(timeout=5) == 0
        finally:
            _receipt(process, tmp_path, "handle-inheritance")
    value = json.loads((tmp_path / "stdout.bin").read_text())
    assert value is None or not value.lower().endswith("private-sentinel")


@WINDOWS
def test_owner_death_kills_inner_job_without_killing_the_outer_job(tmp_path):
    """Retained outer containment makes a failed death control safe to inspect."""
    ready = tmp_path / "inner-ready"
    inner = (
        "import sys,time\n"
        f"sys.path.insert(0,{str(Path(__file__).parent)!r})\n"
        "from windows_process_owner import WindowsOwnedProcess\n"
        "from pathlib import Path\n"
        f"root=Path({str(tmp_path)!r})\n"
        "with (root/'inner-out').open('wb') as out,(root/'inner-err').open('wb') as err:\n"
        " process=WindowsOwnedProcess([sys.executable,'-I','-S','-B','-c',"
        "'import time;time.sleep(30)'],cwd=root,stdout=out,stderr=err)\n"
        f" Path({str(ready)!r}).write_text('ready')\n"
        " time.sleep(30)\n"
    )
    outer = _launch(tmp_path, inner)
    try:
        _wait_for(ready)
        assert outer.active_processes() >= 2
        # Kill this retained, identified parent handle only. The outer job stays open.
        owner._check(outer._api.terminate_process(outer._process, 1))
        assert outer.wait(timeout=5) != 0
        deadline = time.monotonic() + 2
        while outer.active_processes() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert outer.active_processes() == 0
    finally:
        _receipt(outer, tmp_path, "owner-death")


@WINDOWS
@pytest.mark.parametrize("fault", ["query", "terminate", "close-after-native", "cleanup-interrupt"])
def test_uncertain_cleanup_quarantines_launches_without_replaying_handles(tmp_path, fault):
    """Faulted inner owners exit inside a separately retained, verified outer job."""
    result = tmp_path / "uncertain-cleanup.json"
    code = (
        "import json,sys,time\n"
        f"sys.path.insert(0,{str(Path(__file__).parent)!r})\n"
        "import windows_process_owner as owner\n"
        "from pathlib import Path\n"
        f"root=Path({str(tmp_path)!r});fault={fault!r}\n"
        "with (root/'fault-out').open('wb') as out,(root/'fault-err').open('wb') as err:\n"
        " p=owner.WindowsOwnedProcess([sys.executable,'-I','-S','-B','-c',"
        "'import time;time.sleep(30)'],cwd=root,stdout=out,stderr=err)\n"
        " original=ValueError('original fictional failure')\n"
        " native_close=p._api.close\n"
        " close_calls=[]\n"
        " def failed_query(*args):raise OSError('controlled query failure')\n"
        " def failed_terminate(*args):raise OSError('controlled termination failure')\n"
        " def interrupted_terminate(*args):raise KeyboardInterrupt('controlled cleanup interrupt')\n"
        " def uncertain_close(handle):\n"
        "  close_calls.append(handle)\n"
        "  owner._check(native_close(handle))\n"
        "  if handle==p._job:raise KeyboardInterrupt('controlled interrupt after native close')\n"
        "  return True\n"
        " if fault=='query':p._api.query_job=failed_query\n"
        " elif fault=='terminate':p._api.terminate_job=failed_terminate\n"
        " elif fault=='cleanup-interrupt':p._api.terminate_job=interrupted_terminate\n"
        " else:p._api.close=uncertain_close\n"
        " try:\n"
        "  with p:raise original\n"
        " except ValueError as caught:\n"
        "  assert caught is original\n"
        "  proof=caught.owned_tree\n"
        " else:raise AssertionError('first failure was lost')\n"
        " assert not proof['clean'] and proof['errors']\n"
        " count=len(close_calls)\n"
        " assert p.finish() is proof and len(close_calls)==count\n"
        " try:\n"
        "  owner.WindowsOwnedProcess([sys.executable,'-c','raise AssertionError()'],"
        "cwd=root,stdout=None,stderr=None)\n"
        " except OSError as refusal:assert 'quarantined' in str(refusal)\n"
        " else:raise AssertionError('a new owner ran after unproven cleanup')\n"
        f" Path({str(result)!r}).write_text(json.dumps("
        "{'fault':fault,'proof':proof,'quarantined':True,'close_replayed':False}),encoding='utf-8')\n"
        # No attempt to recover/reclose potentially reused numeric handles.
    )
    outer = _launch(tmp_path, code)
    try:
        assert outer.wait(timeout=5) == 0, (tmp_path / "stderr.bin").read_bytes()
        value = json.loads(result.read_text(encoding="utf-8"))
        assert value["quarantined"] and value["close_replayed"] is False
        assert value["proof"]["clean"] is False
        deadline = time.monotonic() + 2
        while outer.active_processes() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert outer.active_processes() == 0
    finally:
        _receipt(outer, tmp_path, "outer-cleanup-fault-" + fault)
    destination = os.environ.get("SINTER_STARTUP_DIAGNOSTICS_DIR")
    if destination:
        (Path(destination) / ("inner-uncertain-" + fault + ".json")).write_text(
            json.dumps(value, indent=2), encoding="utf-8",
        )


@WINDOWS
def test_raw_cmd_keeps_original_quoting_normal_application_flags_and_status(tmp_path, monkeypatch):
    script = tmp_path / "raw Ω & (draft)! 100%.bat"
    entry = tmp_path / "entry Ω ! 100%.py"
    entry.write_text(
        "import json,sys\n"
        "print(json.dumps({'args':sys.argv[1:], 'isolated':sys.flags.isolated, "
        "'no_site':sys.flags.no_site}),flush=True)\nraise SystemExit(7)\n",
        encoding="utf-8",
    )
    script.write_text(
        '@echo off\nsetlocal EnableExtensions DisableDelayedExpansion\n'
        '"%SINTER_RAW_PYTHON%" "%SINTER_RAW_ENTRY%" %*\nexit /b %errorlevel%\n',
        encoding="utf-8", newline="\r\n",
    )
    monkeypatch.setenv("SINTER_RAW_PYTHON", sys.executable)
    monkeypatch.setenv("SINTER_RAW_ENTRY", str(entry))
    arguments = ["review", "notes Ω & (draft)! 100% ready.txt", "--offline"]
    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    invocation = subprocess.list2cmdline([str(script), *arguments])
    command = f'{shell} /d /s /c "{invocation}"'
    with (tmp_path / "raw-out").open("wb") as out, (tmp_path / "raw-err").open("wb") as err:
        process = owner.WindowsOwnedProcess(
            command, executable=os.environ["COMSPEC"], cwd=tmp_path, stdout=out, stderr=err,
        )
    try:
        assert process.wait(timeout=5) == 7
    finally:
        proof = _receipt(process, tmp_path, "raw-cmd")
    assert json.loads((tmp_path / "raw-out").read_text()) == {
        "args": arguments, "isolated": 0, "no_site": 0,
    }
    assert process.args == command
    assert proof["process_counts_after"]["total_processes"] >= 2


@WINDOWS
def test_interrupted_resume_retains_partial_work_and_unknown_resume_outcome(tmp_path, monkeypatch):
    marker = tmp_path / "partial.txt"
    api = owner._WinAPI()
    native = api.resume
    original = KeyboardInterrupt("controlled interrupt after native resume")

    def interrupted_resume(thread):
        assert native(thread) == 1
        _wait_for(marker)
        raise original

    monkeypatch.setattr(api, "resume", interrupted_resume)
    with pytest.raises(KeyboardInterrupt) as caught:
        _launch(tmp_path, (
            f"open({str(marker)!r},'w').write('fictional partial retained')\n"
            "import time;time.sleep(30)\n"
        ), _api=api)
    assert caught.value is original
    proof = caught.value.owned_tree
    assert proof["clean"] and proof["parent_reaped"] and proof["active_after"] == 0
    assert proof["resume_outcome"] == "unconfirmed" and proof["resumed"] is False
    assert marker.read_text() == "fictional partial retained"
    destination = os.environ.get("SINTER_STARTUP_DIAGNOSTICS_DIR")
    if destination:
        (Path(destination) / "after-native-resume.json").write_text(
            json.dumps(proof, indent=2), encoding="utf-8",
        )


@WINDOWS
def test_owned_observer_keeps_five_second_wait_and_separate_cleanup_proof(tmp_path):
    import wrapper_diagnostics

    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    value, raw = wrapper_diagnostics.observe_wrapper(
        f'{shell} /d /s /c "exit /b 7"', tmp_path, tmp_path / "no-marker",
        timeout=5, phase_paths={"batch": tmp_path / "no-batch"},
        windows_tree=True, windows_executable=os.environ["COMSPEC"],
    )
    assert value["returncode_before_cleanup"] == value["returncode"] == 7
    assert value["timed_out"] is False and value["cleanup_errors"] == []
    assert value["owned_tree"]["clean"] and value["owned_tree"]["active_after"] == 0
    assert value["phase_timing"]["wait_budget_seconds"] == 5
    assert value["owned_cleanup_budget_seconds"] == 2
    assert value["full_owned_elapsed_seconds"] >= 0
    assert value["descendants_observed"] is False
    assert value["stdout"]["final_stream_proven"] is False
    assert raw == b""


@WINDOWS
def test_owned_observer_preserves_interruption_after_real_creation(tmp_path, monkeypatch):
    import wrapper_diagnostics

    api = owner._WinAPI()
    native = api.create
    original = KeyboardInterrupt("controlled observer creation interrupt")

    def interrupted_create(*args):
        owner._check(native(*args))
        raise original

    monkeypatch.setattr(api, "create", interrupted_create)
    monkeypatch.setattr(owner, "_WinAPI", lambda: api)
    shell = subprocess.list2cmdline([os.environ["COMSPEC"]])
    with pytest.raises(KeyboardInterrupt) as caught:
        wrapper_diagnostics.observe_wrapper(
            f'{shell} /d /s /c "exit /b 0"', tmp_path, tmp_path / "no-marker",
            timeout=5, windows_tree=True, windows_executable=os.environ["COMSPEC"],
        )
    assert caught.value is original
    value = caught.value.wrapper_observation
    assert value["owned_tree"]["clean"] and value["owned_tree"]["process_created"]
    assert value["owned_tree"]["parent_reaped"] and value["owned_tree"]["active_after"] == 0
    assert value["stdout"]["sample_base64"] == ""
    assert value["stderr"]["sample_base64"] == ""
    assert "error" in value["marker"]


@WINDOWS
def test_owned_observer_retains_partial_samples_and_original_wait_interruption(tmp_path, monkeypatch):
    import wrapper_diagnostics

    marker = tmp_path / "partial-marker.json"
    native = owner.WindowsOwnedProcess.wait
    original = KeyboardInterrupt("controlled observer wait interrupt")
    def interrupted_wait(process, timeout=None):
        _wait_for(marker)
        monkeypatch.setattr(owner.WindowsOwnedProcess, "wait", native)
        raise original
    monkeypatch.setattr(owner.WindowsOwnedProcess, "wait", interrupted_wait)
    with pytest.raises(KeyboardInterrupt) as caught:
        wrapper_diagnostics.observe_wrapper(
            [sys.executable, "-I", "-S", "-B", "-c",
             "import sys,time;from pathlib import Path;"
             "print('fictional partial stdout',flush=True);"
             "print('fictional partial stderr',file=sys.stderr,flush=True);"
             f"Path({str(marker)!r}).write_text('{{\"partial\":true}}');"
             "time.sleep(30)"],
            tmp_path, marker, timeout=5, windows_tree=True,
        )
    assert caught.value is original
    value = caught.value.wrapper_observation
    assert value["owned_tree"]["clean"] and value["owned_tree"]["active_after"] == 0
    assert value["owned_tree"]["parent_reaped"] and value["marker"]["value"] == {"partial": True}
    assert value["stdout"]["sample_bytes"] > 0 and value["stderr"]["sample_bytes"] > 0
    assert value["stdout"]["metadata_stable_snapshot"] and value["stderr"]["metadata_stable_snapshot"]
    assert marker.read_text() == '{"partial":true}'
    monkeypatch.setattr(owner.WindowsOwnedProcess, "wait", native)
    destination = os.environ.get("SINTER_STARTUP_DIAGNOSTICS_DIR")
    if destination:
        (Path(destination) / "observer-interrupted-partial.json").write_text(
            json.dumps(value, indent=2), encoding="utf-8",
        )
