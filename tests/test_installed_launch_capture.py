"""Atomic opener evidence regressions; no app, browser, container or model runs."""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path

import pytest

from tools import installed_workflow_browser as flow

URL = "http://127.0.0.1:12345"


@pytest.fixture
def capture_root(tmp_path):
    """Use an exact directory on macOS hosts with a /var symbolic-link prefix."""
    return tmp_path.resolve(strict=True)


class Clock:
    def __init__(self, step=None):
        self.elapsed = 0.0
        self.waits = []
        self.step = step

    def now(self):
        return self.elapsed

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.elapsed += seconds
        if self.step is not None:
            self.step()


def read(path, clock, alive=lambda: True, **kwargs):
    return flow.read_launch_capture(
        path, alive, clock=clock.now, sleep=clock.sleep, **kwargs
    )


def test_capture_is_exact_exclusive_and_closed_before_publication(capture_root):
    path = capture_root / "launch-url.txt"
    flow.publish_launch_capture(path, URL)
    assert path.read_bytes() == URL.encode("ascii")
    assert not flow.launch_capture_pending(path).exists()
    assert path.stat().st_nlink == 1
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read(path, Clock()) == URL.encode("ascii")
    with pytest.raises(FileExistsError):
        flow.publish_launch_capture(path, "http://127.0.0.1:12346")
    assert path.read_bytes() == URL.encode("ascii")
    assert not flow.launch_capture_pending(path).exists()


def test_existing_pending_is_preserved_without_final_publication(capture_root):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    pending.write_bytes(b"Retained incomplete capture")
    with pytest.raises(FileExistsError):
        flow.publish_launch_capture(path, URL)
    assert pending.read_bytes() == b"Retained incomplete capture"
    assert not path.exists()


@pytest.mark.parametrize("target", ["final", "pending"])
def test_producer_does_not_replace_symlinked_existing_evidence(capture_root, target):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    earlier = capture_root / "retained-earlier-evidence"
    earlier.write_bytes(b"Retained unrelated bytes")
    redirect = path if target == "final" else pending
    try:
        redirect.symlink_to(earlier)
    except OSError:
        pytest.skip("This user cannot create the explicit symlink refusal fixture.")
    with pytest.raises(FileExistsError):
        flow.publish_launch_capture(path, URL)
    assert redirect.is_symlink()
    assert earlier.read_bytes() == b"Retained unrelated bytes"


@pytest.mark.parametrize(
    "prefix", [b"", b"http://127.0.0.1:12"], ids=["empty", "valid-prefix"]
)
def test_ready_reader_does_not_admit_creation_or_valid_prefix_window(
    capture_root, monkeypatch, prefix
):
    path = capture_root / "launch-url.txt"
    entered = threading.Event()
    resume = threading.Event()
    finished = threading.Event()
    errors = []
    original_write = os.write
    original_open = Path.open

    def paused_write(descriptor, raw):
        if prefix:
            assert original_write(descriptor, prefix) == len(prefix)
        entered.set()
        assert resume.wait(5)
        assert original_write(descriptor, raw[len(prefix) :]) == len(raw) - len(prefix)
        return len(raw)

    def paused_legacy_open(target, *args, **kwargs):
        stream = original_open(target, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode")
        if target == path and mode == "w":
            # The exact former Path.write_text producer exposes an empty final
            # before returning its stream. This branch supports the RED control.
            entered.set()
            assert resume.wait(5)
        return stream

    def publish():
        try:
            flow.publish_launch_capture(path, URL)
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    monkeypatch.setattr(flow.os, "write", paused_write)
    monkeypatch.setattr(Path, "open", paused_legacy_open)
    thread = threading.Thread(target=publish)
    thread.start()
    assert entered.wait(5)

    def progress():
        resume.set()
        assert finished.wait(5)

    clock = Clock(progress)
    try:
        raw = read(path, clock)
        assert raw == URL.encode("ascii")
        assert flow.inner_address(raw.decode("ascii")) == ("127.0.0.1", 12345)
        assert clock.waits == [0.02]
    finally:
        resume.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and errors == []


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://127.0.0.1:12345\n",
        "http://localhost:12345",
        "https://127.0.0.1:12345",
        "http://user:secret@127.0.0.1:12345",
        "http://127.0.0.1:12345/",
        "http://127.0.0.1:12345/path",
        "http://127.0.0.1:12345?token=fictional-secret",
        "http://127.0.0.1:12345#fragment",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:１２３４５",
    ],
)
def test_invalid_producer_argument_never_creates_capture(capture_root, value):
    path = capture_root / "launch-url.txt"
    with pytest.raises(ValueError):
        flow.publish_launch_capture(path, value)
    assert not path.exists() and not flow.launch_capture_pending(path).exists()


@pytest.mark.parametrize("raw", [b"", b"http://127.0.0.1:12345\n", b"\xff"])
def test_invalid_complete_final_is_rejected_immediately(capture_root, raw):
    path = capture_root / "launch-url.txt"
    path.write_bytes(raw)
    clock = Clock()
    with pytest.raises((ValueError, UnicodeDecodeError)):
        read(path, clock)
    assert clock.waits == [] and path.read_bytes() == raw


def test_missing_capture_retains_original_bounded_deadline(capture_root):
    clock = Clock()
    with pytest.raises(ValueError, match="failed before fixed opener capture"):
        read(capture_root / "launch-url.txt", clock)
    assert clock.elapsed == 25.0
    assert all(0 < duration <= 0.02 for duration in clock.waits)


@pytest.mark.parametrize("phase", ["waiting", "after_read"])
def test_dead_original_producer_never_admits_capture(capture_root, phase):
    path = capture_root / "launch-url.txt"
    if phase == "after_read":
        flow.publish_launch_capture(path, URL)
    observed = []

    def alive():
        observed.append(True)
        return phase == "after_read" and len(observed) == 1

    with pytest.raises(ValueError, match="failed before|exited before"):
        read(path, Clock(), alive)
    assert len(observed) == (2 if phase == "after_read" else 1)


@pytest.mark.parametrize("transition", ["already_linked", "link", "unlink"])
def test_known_atomic_link_transitions_wait_for_committed_single_link(
    capture_root, monkeypatch, transition
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    pending.write_bytes(URL.encode("ascii"))
    if transition != "link":
        os.link(pending, path)
    ordinary_stat = flow._capture_stat
    changed = False

    def observed(target, links):
        nonlocal changed
        result = ordinary_stat(target, links)
        if target == pending and not changed:
            changed = True
            if transition == "link":
                os.link(pending, path)
            elif transition == "unlink":
                pending.unlink()
        return result

    monkeypatch.setattr(flow, "_capture_stat", observed)
    clock = Clock(lambda: pending.unlink(missing_ok=True))
    assert read(path, clock) == URL.encode("ascii")
    assert clock.waits == [0.02] and path.stat().st_nlink == 1


def test_foreign_pending_final_pair_is_not_readiness(capture_root):
    path = capture_root / "launch-url.txt"
    path.write_bytes(URL.encode("ascii"))
    flow.launch_capture_pending(path).write_bytes(URL.encode("ascii"))
    with pytest.raises(ValueError, match="publication identity differs"):
        read(path, Clock())
    assert path.read_bytes() == URL.encode("ascii")


def test_hardlinked_final_without_pending_is_not_admitted(capture_root):
    path = capture_root / "launch-url.txt"
    original = capture_root / "unrelated.txt"
    original.write_bytes(URL.encode("ascii"))
    os.link(original, path)
    with pytest.raises(ValueError, match="unowned, redirected or over bound"):
        read(path, Clock())


def test_symlink_capture_is_not_followed(capture_root):
    path = capture_root / "launch-url.txt"
    original = capture_root / "unrelated.txt"
    original.write_bytes(URL.encode("ascii"))
    try:
        path.symlink_to(original)
    except OSError:
        pytest.skip("This user cannot create the explicit symlink refusal fixture.")
    with pytest.raises(ValueError, match="unowned, redirected or over bound"):
        read(path, Clock())


def test_oversized_capture_remains_intact_and_refuses(capture_root):
    path = capture_root / "launch-url.txt"
    raw = b"x" * (flow.MAX_LAUNCH_CAPTURE + 1)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="over bound"):
        read(path, Clock())
    assert path.read_bytes() == raw


@pytest.mark.parametrize("operation", ["write", "fsync", "close", "link"])
def test_publication_fault_keeps_first_error_and_never_exposes_final(
    capture_root, monkeypatch, operation
):
    path = capture_root / "launch-url.txt"
    first = OSError("Injected " + operation + " failure")
    original = getattr(flow.os, operation)

    def fail(*args, **kwargs):
        if operation == "close":
            original(*args, **kwargs)
        raise first

    monkeypatch.setattr(flow.os, operation, fail)
    with pytest.raises(OSError) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first
    assert not path.exists() and not flow.launch_capture_pending(path).exists()


def test_short_write_refuses_instead_of_publishing_a_valid_prefix(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    original = os.write

    def short(descriptor, raw):
        return original(descriptor, b"http://127.0.0.1:12")

    monkeypatch.setattr(flow.os, "write", short)
    with pytest.raises(OSError, match="write was incomplete"):
        flow.publish_launch_capture(path, URL)
    assert not path.exists() and not flow.launch_capture_pending(path).exists()


@pytest.mark.parametrize("removed", [False, True])
def test_publication_unlink_fault_retains_evidence_and_refusal_marker(
    capture_root, monkeypatch, removed
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    original = Path.unlink
    first = OSError("Injected commit unlink failure")
    calls = []

    def unlink(target, **kwargs):
        calls.append(target.name)
        if target == pending and len(calls) == 1:
            if removed:
                original(target, **kwargs)
            raise first
        return original(target, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first
    assert calls == [pending.name]
    assert first.launch_capture_uncertain is True
    assert path.read_bytes() == pending.read_bytes() == URL.encode("ascii")
    assert path.stat().st_nlink == pending.stat().st_nlink == 2
    with pytest.raises(ValueError, match="failed before fixed opener capture"):
        read(path, Clock(), timeout=0.04)


def test_uncertain_link_outcome_retains_exact_published_evidence(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    first = OSError("Injected post-link acknowledgement failure")
    original = os.link

    def link(*args, **kwargs):
        original(*args, **kwargs)
        raise first

    monkeypatch.setattr(flow.os, "link", link)
    with pytest.raises(OSError) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first
    assert first.launch_capture_uncertain is True
    assert path.read_bytes() == pending.read_bytes() == URL.encode("ascii")
    assert path.stat().st_nlink == pending.stat().st_nlink == 2
    clock = Clock()
    with pytest.raises(ValueError, match="failed before fixed opener capture"):
        read(path, clock, timeout=0.04)
    assert clock.waits == [0.02, 0.02]


def test_refusal_marker_restoration_error_remains_an_unacknowledged_publication(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    first = OSError("Injected unlink acknowledgement failure")
    later = OSError("Injected marker restoration failure")
    original_unlink = Path.unlink
    original_link = os.link

    def unlink(target, **kwargs):
        original_unlink(target, **kwargs)
        raise first

    def link(source, target, **kwargs):
        if target == pending:
            raise later
        return original_link(source, target, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(flow.os, "link", link)
    with pytest.raises(OSError) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first and first.launch_capture_uncertain is True
    assert first.launch_capture_cleanup == (
        ("pending refusal marker retention", later),
    )
    assert path.read_bytes() == URL.encode("ascii") and not pending.exists()
    # The retained address is not an acknowledgement of the failed publisher.
    # Files alone cannot recover that acknowledgement if restoring its marker
    # also fails. A stopped original app still prevents address admission.
    assert read(path, Clock()) == URL.encode("ascii")
    with pytest.raises(ValueError, match="failed before fixed opener capture"):
        read(path, Clock(), alive=lambda: False)


def test_rebound_pending_is_retained_and_never_cleaned_as_owned(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    preserved = capture_root / "original-pending"
    original = os.write

    def rebound(descriptor, raw):
        result = original(descriptor, raw)
        pending.rename(preserved)
        pending.write_bytes(b"Unrelated rebound evidence")
        return result

    monkeypatch.setattr(flow.os, "write", rebound)
    with pytest.raises(ValueError, match="changed before publication") as raised:
        flow.publish_launch_capture(path, URL)
    assert not path.exists()
    assert preserved.read_bytes() == URL.encode("ascii")
    assert pending.read_bytes() == b"Unrelated rebound evidence"
    assert raised.value.launch_capture_cleanup[0][0] == "pending capture removal"


def test_descriptor_named_mismatch_before_write_keeps_unrelated_evidence(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    pending = flow.launch_capture_pending(path)
    preserved = capture_root / "original-pending"
    original = os.open

    def rebound(*args, **kwargs):
        descriptor = original(*args, **kwargs)
        pending.rename(preserved)
        pending.write_bytes(b"Unrelated rebound evidence")
        return descriptor

    monkeypatch.setattr(flow.os, "open", rebound)
    with pytest.raises(ValueError, match="descriptor differs") as raised:
        flow.publish_launch_capture(path, URL)
    assert not path.exists() and preserved.read_bytes() == b""
    assert pending.read_bytes() == b"Unrelated rebound evidence"
    assert raised.value.launch_capture_cleanup[0][0] == "pending capture removal"


@pytest.mark.parametrize("path_kind", ["relative", "missing", "symlink-parent"])
def test_invalid_producer_path_refuses_without_creating_final(capture_root, path_kind):
    if path_kind == "relative":
        path = Path("not-an-absolute-capture") / "launch-url.txt"
    elif path_kind == "missing":
        path = capture_root / "missing" / "launch-url.txt"
    else:
        link = capture_root / "linked"
        try:
            link.symlink_to(capture_root, target_is_directory=True)
        except OSError:
            pytest.skip("This user cannot create the parent-symlink refusal fixture.")
        path = link / "launch-url.txt"
    with pytest.raises((ValueError, FileNotFoundError)):
        flow.publish_launch_capture(path, URL)
    assert not path.exists()


def test_body_fault_retains_independent_close_and_cleanup_faults(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    first = OSError("Injected write failure")
    close_fault = OSError("Injected close failure")
    unlink_fault = OSError("Injected pending cleanup failure")
    original_close = os.close

    def fail_write(*args):
        raise first

    def fail_close(descriptor):
        original_close(descriptor)
        raise close_fault

    def fail_unlink(*args, **kwargs):
        raise unlink_fault

    monkeypatch.setattr(flow.os, "write", fail_write)
    monkeypatch.setattr(flow.os, "close", fail_close)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first
    assert first.launch_capture_cleanup == (
        ("descriptor close", close_fault),
        ("pending capture removal", unlink_fault),
    )
    assert not path.exists() and flow.launch_capture_pending(path).exists()


def test_hostile_first_exception_keeps_identity_and_all_cleanup_outcomes(
    capture_root, monkeypatch
):
    class Hostile(OSError):
        def __bool__(self):
            raise AssertionError("Exception truth must not be evaluated")

        def __str__(self):
            raise AssertionError("Exception text must not be evaluated")

        def __setattr__(self, name, value):
            raise AssertionError("Exception attribute override must not be called")

    path = capture_root / "launch-url.txt"
    first = Hostile("Injected first body failure")
    later = OSError("Injected cleanup failure")
    original = os.close
    calls = []

    def write(*args):
        raise first

    def close(descriptor):
        calls.append("close")
        original(descriptor)
        raise later

    def unlink(*args, **kwargs):
        calls.append("unlink")
        raise later

    monkeypatch.setattr(flow.os, "write", write)
    monkeypatch.setattr(flow.os, "close", close)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(Hostile) as raised:
        flow.publish_launch_capture(path, URL)
    assert raised.value is first and calls == ["close", "unlink"]
    assert first.launch_capture_cleanup == (
        ("descriptor close", later),
        ("pending capture removal", later),
    )


def test_read_fault_keeps_identity_and_later_descriptor_close(
    capture_root, monkeypatch
):
    path = capture_root / "launch-url.txt"
    flow.publish_launch_capture(path, URL)
    first = OSError("Injected read failure")
    later = OSError("Injected read close failure")
    original_close = os.close

    def fail_read(*args):
        raise first

    def fail_close(descriptor):
        original_close(descriptor)
        raise later

    monkeypatch.setattr(flow.os, "read", fail_read)
    monkeypatch.setattr(flow.os, "close", fail_close)
    with pytest.raises(OSError) as raised:
        read(path, Clock())
    assert raised.value is first
    assert first.launch_capture_cleanup == (("capture read close", later),)


def test_reader_detects_file_changed_during_read(capture_root, monkeypatch):
    path = capture_root / "launch-url.txt"
    flow.publish_launch_capture(path, URL)
    original_read = os.read
    changed = False

    def change(descriptor, size):
        nonlocal changed
        raw = original_read(descriptor, size)
        if not changed:
            changed = True
            path.write_bytes(b"http://127.0.0.1:12346")
        return raw

    monkeypatch.setattr(flow.os, "read", change)
    with pytest.raises(ValueError, match="changed during its exact read"):
        read(path, Clock())
