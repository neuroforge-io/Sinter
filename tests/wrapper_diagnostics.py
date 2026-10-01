"""Bounded observations for the zero-work platform launcher fixtures."""

import base64
import hashlib
import json
import subprocess
from pathlib import Path

MAX_SNAPSHOT_BYTES = 65536
MAX_SAMPLE_BYTES = 4096
REAP_TIMEOUT = 1


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


def observe_wrapper(
    command, directory: Path, marker: Path, timeout=5
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
    process = None
    phase = "launch"
    # Do not use Popen as a context manager: its exit may wait without a bound.
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
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
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                observation["timed_out"] = True
            observation["returncode_before_cleanup"] = process.poll()
        except OSError as exc:
            observation["operation_error"] = {
                "phase": phase,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            if process is not None:
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
    observation["stdout"], stdout_data = _snapshot(stdout_path)
    observation["stderr"], _ = _snapshot(stderr_path)
    observation["marker"], marker_data = _snapshot(marker, limit=MAX_SAMPLE_BYTES)
    if marker_data is not None:
        try:
            observation["marker"]["value"] = json.loads(marker_data)
        except (UnicodeError, ValueError) as exc:
            observation["marker"]["parse_error"] = f"{type(exc).__name__}: {exc}"
    return observation, stdout_data
