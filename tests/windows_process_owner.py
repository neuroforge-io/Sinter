"""Windows-only ownership for finite launcher qualification, not app launching.

Windows 10 / Server 2016 or newer is required for atomic JOB_LIST assignment.
No fallback may execute a child outside the private kill-on-close job.
"""

import ctypes
import math
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("attributes", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("pid", wintypes.DWORD),
        ("tid", wintypes.DWORD),
    ]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "read_operations", "write_operations", "other_operations",
        "read_bytes", "write_bytes", "other_bytes",
    )]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_longlong),
        ("kernel_time", ctypes.c_longlong),
        ("period_user_time", ctypes.c_longlong),
        ("period_kernel_time", ctypes.c_longlong),
        ("page_faults", wintypes.DWORD),
        ("total_processes", wintypes.DWORD),
        ("active_processes", wintypes.DWORD),
        ("terminated_processes", wintypes.DWORD),
    ]


class _WinAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise OSError("This qualification owner requires Windows 10 or newer.")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        ptr = ctypes.c_void_p
        handle = wintypes.HANDLE
        word = wintypes.DWORD

        def bind(name, result, *arguments):
            function = getattr(kernel, name)
            function.restype = result
            function.argtypes = list(arguments)
            return function

        self.close = bind("CloseHandle", wintypes.BOOL, handle)
        self.current = bind("GetCurrentProcess", handle)
        self.duplicate = bind("DuplicateHandle", wintypes.BOOL,
                              handle, handle, handle, ctypes.POINTER(handle),
                              word, wintypes.BOOL, word)
        self.create_job = bind("CreateJobObjectW", handle, ptr, wintypes.LPCWSTR)
        self.set_job = bind("SetInformationJobObject", wintypes.BOOL,
                            handle, ctypes.c_int, ptr, word)
        self.query_job = bind("QueryInformationJobObject", wintypes.BOOL,
                              handle, ctypes.c_int, ptr, word, ptr)
        self.terminate_job = bind("TerminateJobObject", wintypes.BOOL, handle, wintypes.UINT)
        self.initialize = bind("InitializeProcThreadAttributeList", wintypes.BOOL,
                               ptr, word, word, ctypes.POINTER(ctypes.c_size_t))
        self.update = bind("UpdateProcThreadAttribute", wintypes.BOOL,
                           ptr, word, ctypes.c_size_t, ptr, ctypes.c_size_t, ptr, ptr)
        self.delete_attributes = bind("DeleteProcThreadAttributeList", None, ptr)
        self.create = bind("CreateProcessW", wintypes.BOOL,
                           wintypes.LPCWSTR, wintypes.LPWSTR, ptr, ptr,
                           wintypes.BOOL, word, ptr, wintypes.LPCWSTR,
                           ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInfo))
        self.in_job = bind("IsProcessInJob", wintypes.BOOL,
                           handle, handle, ctypes.POINTER(wintypes.BOOL))
        self.resume = bind("ResumeThread", word, handle)
        self.wait = bind("WaitForSingleObject", word, handle, word)
        self.exit_code = bind("GetExitCodeProcess", wintypes.BOOL,
                              handle, ctypes.POINTER(word))
        self.terminate_process = bind("TerminateProcess", wintypes.BOOL, handle, wintypes.UINT)
        self.process_times = bind("GetProcessTimes", wintypes.BOOL, handle,
                                  ctypes.POINTER(wintypes.FILETIME),
                                  ctypes.POINTER(wintypes.FILETIME),
                                  ctypes.POINTER(wintypes.FILETIME),
                                  ctypes.POINTER(wintypes.FILETIME))
        self.image = bind("QueryFullProcessImageNameW", wintypes.BOOL,
                          handle, word, wintypes.LPWSTR, ctypes.POINTER(word))


def _check(success):
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())


_UNRESOLVED_OWNERS = {}


class WindowsOwnedProcess:
    """Own one explicit executable and its descendants, including on owner death."""

    def __init__(self, command, *, cwd, stdout, stderr, executable=None, _api=None):
        if _UNRESOLVED_OWNERS:
            raise OSError("A prior Windows owner has unproven cleanup; further launches are quarantined.")
        self._api = _api if _api is not None else _WinAPI()
        if isinstance(command, str):
            if not command or "\x00" in command or executable is None:
                raise ValueError("A raw command requires an explicit absolute executable.")
            self.args = command
            line = command  # Preserve CMD quoting verbatim, without argv re-escaping.
            application = os.fspath(executable)
        elif isinstance(command, (list, tuple)) and command:
            self.args = [os.fspath(value) for value in command]
            if any("\x00" in value for value in self.args):
                raise ValueError("A process argument contains a null character.")
            if executable is not None:
                raise ValueError("Only raw commands take an explicit executable.")
            application = self.args[0]
            line = subprocess.list2cmdline(self.args)
        else:
            raise ValueError("Pass a nonempty argument sequence or explicit raw command.")
        if not Path(application).is_absolute():
            raise ValueError("The qualification executable must be absolute.")
        # Register output storage before any native call can populate it.
        self._info = _ProcessInfo()
        self.returncode = None
        self.identity = {}
        self._job = None
        self._resumed = False
        self._resume_outcome = 'not_attempted'
        self._receipt = None
        duplicates = []
        attribute_buffer = None
        attribute_initialized = False
        setup_error = None
        setup_close_errors = []
        try:
            self._job = self._api.create_job(None, None)
            _check(self._job)
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
            _check(self._api.set_job(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            size = ctypes.c_size_t()
            self._api.initialize(None, 2, 0, ctypes.byref(size))
            if not size.value or size.value > 65536:
                raise OSError("Windows refused the bounded process attribute list.")
            attribute_buffer = ctypes.create_string_buffer(size.value)
            _check(self._api.initialize(attribute_buffer, 2, 0, ctypes.byref(size)))
            attribute_initialized = True
            # Duplicate only these streams, without changing caller handle flags.
            import msvcrt
            with open(os.devnull, "rb") as stdin:
                for stream in (stdin, stdout, stderr):
                    duplicate = wintypes.HANDLE()
                    duplicates.append(duplicate)
                    _check(self._api.duplicate(
                        self._api.current(), msvcrt.get_osfhandle(stream.fileno()),
                        self._api.current(), ctypes.byref(duplicate), 0, True, 2,
                    ))
            inherited_values = [handle.value for handle in duplicates]
            inherited = (wintypes.HANDLE * 3)(*inherited_values)
            jobs = (wintypes.HANDLE * 1)(self._job)
            _check(self._api.update(attribute_buffer, 0, 0x20002,
                                    inherited, ctypes.sizeof(inherited), None, None))
            # Assignment is atomic with creation, avoiding an unowned suspended child.
            _check(self._api.update(attribute_buffer, 0, 0x2000D,
                                    jobs, ctypes.sizeof(jobs), None, None))
            startup = _StartupInfoEx()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES.
            startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, \
                startup.StartupInfo.hStdError = inherited_values
            startup.attributes = ctypes.cast(attribute_buffer, ctypes.c_void_p)
            line = ctypes.create_unicode_buffer(line)
            _check(self._api.create(
                application, line, None, None, True,
                0x00080004,  # EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED.
                None, os.fspath(cwd), ctypes.byref(startup), ctypes.byref(self._info),
            ))
            self._verify_membership()
            creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
            _check(self._api.process_times(
                self._process, ctypes.byref(creation), ctypes.byref(exit_time),
                ctypes.byref(kernel), ctypes.byref(user),
            ))
            image_size = wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(image_size.value)
            _check(self._api.image(self._process, 0, image, ctypes.byref(image_size)))
            self.identity = {
                "pid": self.pid,
                "creation_filetime": (creation.dwHighDateTime << 32) | creation.dwLowDateTime,
                "image": image.value,
                "atomic_job_assignment": True,
                "membership_verified_before_resume": True,
            }
            self._resume_outcome = "unconfirmed"
            self._resume(self._info.thread)
            self._resumed = True
            self._resume_outcome = "confirmed"
        except BaseException as error:
            setup_error = error
        finally:
            # Attempt every release; a secondary failure never masks the first fault.
            handles = ([self._info.thread] if self._info.thread else [])
            handles.extend(handle.value for handle in duplicates if handle.value)
            for handle in handles:
                try:
                    _check(self._api.close(handle))
                except BaseException as error:
                    setup_close_errors.append(f"{type(error).__name__}: {error}")
                    if setup_error is None:
                        setup_error = error
            if attribute_initialized:
                try:
                    self._api.delete_attributes(attribute_buffer)
                except BaseException as error:
                    setup_close_errors.append(f"{type(error).__name__}: {error}")
                    if setup_error is None:
                        setup_error = error
        self._startup_handles_closed = not setup_close_errors
        if setup_error is not None:
            receipt = self.finish()
            receipt["errors"].extend(setup_close_errors)
            receipt["clean"] = receipt["clean"] and not setup_close_errors
            setup_error.owned_tree = receipt
            raise setup_error

    @property
    def pid(self):
        return self._info.pid or None

    @property
    def _process(self):
        return self._info.process

    @_process.setter
    def _process(self, handle):
        self._info.process = handle

    @property
    def _created(self):
        # PID remains recorded after the retained process handle is released.
        return bool(self._info.pid or self._info.process)

    def _verify_membership(self):
        member = wintypes.BOOL()
        _check(self._api.in_job(self._process, self._job, ctypes.byref(member)))
        if not member.value:
            raise OSError("Windows did not confirm the private job assignment.")

    def _resume(self, thread):
        previous = self._api.resume(thread)
        if previous == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        if previous != 1:
            raise OSError("The initial thread was not suspended exactly once.")

    def active_processes(self):
        if not self._job:
            raise OSError("The private job is already closed.")
        accounting = _Accounting()
        _check(self._api.query_job(
            self._job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None,
        ))
        self._last_accounting = {
            "total_processes": accounting.total_processes,
            "active_processes": accounting.active_processes,
            "terminated_processes": accounting.terminated_processes,
            "user_time_100ns": accounting.user_time,
            "kernel_time_100ns": accounting.kernel_time,
        }
        return accounting.active_processes

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if not self._process:
            return None
        state = self._api.wait(self._process, 0)
        if state == 0x102:
            return None
        if state != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        _check(self._api.exit_code(self._process, ctypes.byref(code)))
        self.returncode = code.value  # Same unsigned DWORD contract as Windows Popen.
        return self.returncode

    def wait(self, timeout):
        if timeout is None or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("A finite nonnegative wait is required.")
        if self.poll() is not None:
            return self.returncode
        state = self._api.wait(self._process, min(0xFFFFFFFE, math.ceil(timeout * 1000)))
        if state == 0x102:
            raise subprocess.TimeoutExpired(self.args, timeout)
        if state != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return self.poll()

    def kill(self):
        _check(self._api.terminate_job(self._job, 1))

    def finish(self, timeout=2):
        """One bounded cleanup deadline; return proof separately from exit status."""
        if self._receipt is not None:
            return self._receipt
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Cleanup needs a finite positive deadline.")
        deadline = time.monotonic() + timeout
        receipt = {
            "schema": "sinter-windows-owned-tree/v1",
            "identity": {"pid": self.pid, **self.identity},
            "process_created": self._created,
            "resumed": self._resumed,
            "resume_outcome": self._resume_outcome,
            "active_before": None,
            "active_after": None,
            "parent_reaped": not self._created,
            "job_handle_closed": self._job is None,
            "process_handle_closed": self._process is None,
            "startup_handles_closed": self._startup_handles_closed,
            "errors": [],
        }
        cleanup_interruption = None
        try:
            if self._job:
                receipt["active_before"] = self.active_processes()
                receipt["process_counts_before"] = dict(self._last_accounting)
                if receipt["active_before"]:
                    self.kill()
                if self._created:
                    self.wait(timeout=max(0, deadline - time.monotonic()))
                    receipt["parent_reaped"] = self.returncode is not None
                while True:
                    receipt["active_after"] = self.active_processes()
                    receipt["process_counts_after"] = dict(self._last_accounting)
                    if receipt["active_after"] == 0:
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Owned Windows job did not become empty.")
                    time.sleep(min(0.01, remaining))
        except BaseException as error:
            receipt["errors"].append(f"{type(error).__name__}: {error}")
            if not isinstance(error, Exception):
                cleanup_interruption = error
        finally:
            # Closing this non-inherited handle also kills the job on owner exit.
            for attribute, label in (("_job", "job_handle_closed"),
                                     ("_process", "process_handle_closed")):
                handle = getattr(self, attribute)
                if handle:
                    try:
                        _check(self._api.close(handle))
                        receipt[label] = True
                    except BaseException as error:
                        receipt["errors"].append(f"close: {type(error).__name__}: {error}")
                        if not isinstance(error, Exception) and cleanup_interruption is None:
                            cleanup_interruption = error
                    else:
                        setattr(self, attribute, None)
        receipt["clean"] = (
            receipt["active_after"] == 0 and receipt["parent_reaped"]
            and receipt["job_handle_closed"] and receipt["process_handle_closed"]
            and receipt["startup_handles_closed"] and not receipt["errors"]
        )
        self._receipt = receipt
        self._cleanup_interruption = cleanup_interruption
        if not receipt["clean"]:
            # Keep identities and possibly live handles; never replay an uncertain close.
            _UNRESOLVED_OWNERS[id(self)] = self
        return receipt

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        receipt = self.finish()
        if self._cleanup_interruption is not None and error is None:
            self._cleanup_interruption.owned_tree = receipt
            raise self._cleanup_interruption
        if not receipt["clean"]:
            if error is not None:
                error.owned_tree = receipt
            else:
                raise OSError("Windows process cleanup is unproven: " + repr(receipt))
        return False
