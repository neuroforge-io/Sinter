"""Bounded observations for the zero-work platform launcher fixtures."""

import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

MAX_SNAPSHOT_BYTES = 65536
MAX_SAMPLE_BYTES = 4096
REAP_TIMEOUT = 1
PHASE_POLL_INTERVAL = 0.05
MAX_PHASE_SAMPLES = 256
PHASES = {
    "batch": frozenset(
        {
            "batch_entered",
            "python_lookup_begin",
            "python_lookup_end",
            "launcher_lookup_begin",
            "launcher_lookup_end",
            "launcher_listing_begin",
            "launcher_listing_end",
            "listed_candidate_entered",
            "tag_filter_begin",
            "tag_filter_end",
            "quote_filter_begin",
            "quote_filter_end",
            "runtime_probe_begin",
            "runtime_probe_end",
            "start_dispatch_begin",
            "start_dispatch_end",
            "batch_finish",
        }
    ),
    "python": frozenset(
        {
            "python_entered",
            "sys_imported",
            "os_imported",
            "json_imported",
            "pathlib_imported",
            "marker_written",
        }
    ),
}


def _sample_phases(
    paths: dict[str, Path],
    timing: dict,
    seen: dict[str, bytes],
    origin: float,
    deadline: float,
) -> None:
    """Retain first host observations of bounded, closed append-only phase lines."""
    for name, path in paths.items():
        if time.monotonic() >= deadline:
            return
        state = timing["streams"][name]
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_SAMPLE_BYTES + 1)
        except FileNotFoundError:
            state["status"] = "not_observed"
            continue
        except OSError as error:
            state["status"] = "read_failed"
            state["read_failures"] += 1
            state["last_read_error"] = f"{type(error).__name__}: {error}"
            continue
        # Timestamp the completed parent read, not the beginning of the poll.
        observed_elapsed = time.monotonic() - origin
        if len(raw) > MAX_SAMPLE_BYTES:
            state["status"] = "oversized"
            continue
        closed = raw[: raw.rfind(b"\n") + 1]
        previous = seen.get(name, b"")
        if not closed.startswith(previous):
            state["status"] = "rewritten"
            continue
        try:
            lines = closed.decode("utf-8").splitlines()
        except UnicodeError:
            state["status"] = "invalid"
            continue
        # The existing Python stage file also retains a runtime= metadata line.
        # It is not a phase and never enters the elapsed-observation payload.
        if any(
            line not in PHASES[name]
            and not (name == "python" and line.startswith("runtime="))
            for line in lines
        ):
            state["status"] = "invalid"
            continue
        old_count = len(previous.splitlines())
        for index, phase in enumerate(lines[old_count:], old_count):
            if phase not in PHASES[name]:
                continue
            if len(timing["samples"]) >= MAX_PHASE_SAMPLES:
                state["status"] = "sample_limit"
                state["samples_truncated"] = True
                break
            timing["samples"].append(
                {
                    "stream": name,
                    "phase": phase,
                    "line_index": index,
                    "first_observed_elapsed_seconds": observed_elapsed,
                }
            )
        else:
            state["status"] = (
                "sample_limit"
                if state["samples_truncated"]
                else "observed"
                if raw and raw.endswith(b"\n")
                else "incomplete"
            )
        seen[name] = closed


def _wait_with_phases(
    process: subprocess.Popen,
    timeout: float,
    paths: dict[str, Path],
    timing: dict,
    origin: float,
) -> None:
    """Sample owned files within one deadline; never reset a wait per poll."""
    # Match the original process.wait(timeout): its budget begins after Popen.
    wait_started = time.monotonic()
    deadline = wait_started + timeout
    timing["wait_started_elapsed_seconds"] = wait_started - origin
    timing["wait_deadline_elapsed_seconds"] = deadline - origin
    timing["wait_budget_seconds"] = timeout
    seen = {}
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if process.poll() is not None:
                return
            raise subprocess.TimeoutExpired(process.args, timeout)
        _sample_phases(paths, timing, seen, origin, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if process.poll() is not None:
                return
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            process.wait(timeout=min(PHASE_POLL_INTERVAL, remaining))
        except subprocess.TimeoutExpired:
            continue
        _sample_phases(paths, timing, seen, origin, deadline)
        return


def _snapshot(path: Path, limit=MAX_SNAPSHOT_BYTES) -> tuple[dict, bytes | None]:
    """Read a bounded snapshot through a handle separate from the writer."""
    try:
        size_before = path.stat().st_size
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        size_after = path.stat().st_size
    except OSError as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}, None
    complete = size_before == size_after == len(data) <= limit
    sample = data[:MAX_SAMPLE_BYTES]
    observation = {
        "size_before": size_before,
        "size_after": size_after,
        "bytes_read": len(data),
        "sample_bytes": len(sample),
        "sample_base64": base64.b64encode(sample).decode("ascii"),
        "sample_sha256": hashlib.sha256(sample).hexdigest(),
        "sample_truncated": max(size_before, size_after) > len(sample),
        "metadata_stable_snapshot": complete,
        "snapshot_sha256": hashlib.sha256(data).hexdigest() if complete else None,
        # A surviving descendant could append after this observation.
        "final_stream_proven": False,
    }
    return observation, data if complete else None


def _wrapper_snapshots(observation, stdout_path, stderr_path, marker):
    observation["stdout"], stdout_data = _snapshot(stdout_path)
    observation["stderr"], _ = _snapshot(stderr_path)
    observation["marker"], marker_data = _snapshot(marker, limit=MAX_SAMPLE_BYTES)
    if marker_data is not None:
        try:
            observation["marker"]["value"] = json.loads(marker_data)
        except (UnicodeError, ValueError) as exc:
            observation["marker"]["parse_error"] = f"{type(exc).__name__}: {exc}"
    return stdout_data


def observe_wrapper(
    command,
    directory: Path,
    marker: Path,
    timeout=5,
    *,
    phase_paths: dict[str, Path] | None = None,
    windows_tree: bool = False,
    windows_executable: str | None = None,
) -> tuple[dict, bytes | None]:
    """Wait for the owned parent, retaining observations even on timeout."""
    stdout_path = directory / "wrapper.stdout.bin"
    stderr_path = directory / "wrapper.stderr.bin"
    observation = {
        "schema": "sinter-wrapper-diagnostics/v1",
        "timeout_seconds": timeout,
        "stdin": "DEVNULL",
        "timed_out": False,
        "pid": None,
        "returncode_before_cleanup": None,
        "returncode": None,
        "parent_exited": False,
        "kill_attempted": False,
        "cleanup_errors": [],
        "descendants_observed": False,
    }
    if phase_paths is not None:
        if not isinstance(phase_paths, dict) or set(phase_paths) - PHASES.keys():
            raise ValueError("Choose only the owned batch and Python phase paths.")
        observation["phase_timing"] = {
            "basis": "Host parent first observations, not exact child boundaries or exclusive CPU time.",
            "origin": "Parent monotonic time before Popen; equal sample times may cover several phases. The wait budget starts after Popen.",
            "poll_interval_seconds": PHASE_POLL_INTERVAL,
            "samples": [],
            "streams": {
                name: {
                    "status": "not_observed",
                    "read_failures": 0,
                    "last_read_error": None,
                    "samples_truncated": False,
                }
                for name in phase_paths
            },
            "final_stream_proven": False,
        }
    process = None
    phase = "launch"
    # Do not use Popen as a context manager: its exit may wait without a bound.
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            try:
                started = time.monotonic() if phase_paths is not None or windows_tree else None
                if windows_tree:
                    from windows_process_owner import WindowsOwnedProcess

                    observation["ownership_mode"] = "windows-job"
                    observation["owned_cleanup_budget_seconds"] = 2
                    if phase_paths is not None:
                        observation["phase_timing"]["origin"] = (
                            "Parent monotonic time before owned process construction; "
                            "the unchanged wait budget starts after construction."
                        )
                    process = WindowsOwnedProcess(
                        command, executable=windows_executable, cwd=directory,
                        stdout=stdout, stderr=stderr,
                    )
                else:
                    process = subprocess.Popen(
                        command,
                        cwd=directory,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                    )
                observation["pid"] = process.pid
                phase = "wait"
                try:
                    if phase_paths is None:
                        process.wait(timeout=timeout)
                    else:
                        _wait_with_phases(
                            process,
                            timeout,
                            phase_paths,
                            observation["phase_timing"],
                            started,
                        )
                except subprocess.TimeoutExpired:
                    observation["timed_out"] = True
                observation["returncode_before_cleanup"] = process.poll()
            except (KeyboardInterrupt, SystemExit) as exc:
                if windows_tree:
                    if hasattr(exc, "owned_tree"):
                        observation["owned_tree"] = exc.owned_tree
                    exc.wrapper_observation = observation
                raise
            except OSError as exc:
                if windows_tree and hasattr(exc, "owned_tree"):
                    observation["owned_tree"] = exc.owned_tree
                    if not exc.owned_tree["clean"]:
                        observation["cleanup_errors"].append("Owned setup cleanup is unproven.")
                observation["operation_error"] = {
                    "phase": phase,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            finally:
                if process is not None and windows_tree:
                    proof = process.finish(timeout=2)
                    observation["owned_tree"] = proof
                    observation["kill_attempted"] = bool(proof["active_before"])
                    observation["returncode"] = process.returncode
                    observation["parent_exited"] = proof["parent_reaped"]
                    observation["full_owned_elapsed_seconds"] = time.monotonic() - started
                    if not proof["clean"]:
                        observation["cleanup_errors"].append("Owned Windows tree cleanup is unproven.")
                    interruption = process._cleanup_interruption
                    if interruption is not None and sys.exc_info()[0] is None:
                        interruption.wrapper_observation = observation
                        raise interruption
                elif process is not None:
                    if process.poll() is None:
                        observation["kill_attempted"] = True
                        try:
                            process.kill()
                        except OSError as exc:
                            observation["cleanup_errors"].append(
                                f"kill: {type(exc).__name__}: {exc}"
                            )
                        try:
                            process.wait(timeout=REAP_TIMEOUT)
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            observation["cleanup_errors"].append(
                                f"wait: {type(exc).__name__}: {exc}"
                            )
                    observation["returncode"] = process.poll()
                    observation["parent_exited"] = process.returncode is not None
    except (KeyboardInterrupt, SystemExit) as exc:
        if windows_tree:
            # Cleanup ran first. Keep bounded partial evidence without replacing the fault.
            exc.wrapper_observation = observation
            try:
                _wrapper_snapshots(observation, stdout_path, stderr_path, marker)
            except BaseException as sample_error:
                observation["interrupted_snapshot_error"] = (
                    f"{type(sample_error).__name__}: {sample_error}"
                )
        raise
    stdout_data = _wrapper_snapshots(observation, stdout_path, stderr_path, marker)
    return observation, stdout_data
