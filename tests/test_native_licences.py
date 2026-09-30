"""The native package must preserve the actual copied libraries' notices."""

from __future__ import annotations

import copy

import pytest

from tools import native_licences as licences


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    runtime, notices = tmp_path / "runtime", tmp_path / "notices"
    origin = tmp_path / "origin" / "libexample.so.1"
    origin.parent.mkdir()
    origin.write_bytes(b"exact library bytes")
    library = runtime / "_internal" / origin.name
    library.parent.mkdir(parents=True)
    library.write_bytes(origin.read_bytes())
    copyright = tmp_path / "doc" / "libexample1" / "copyright"
    copyright.parent.mkdir(parents=True)
    copyright.write_text(
        "Copyright Original Authors. Include this notice.\n"
        "The licence is /usr/share/common-licenses/GPL-3.\n"
    )
    common = tmp_path / "common"
    common.mkdir()
    (common / "GPL-3").write_text("Original common licence text")
    monkeypatch.setattr(
        licences, "package_owner", lambda path: ("libexample1", "1.2-3")
    )
    return {
        "runtime": runtime,
        "notices": notices,
        "sources": {origin.name: [origin]},
        "documentation": tmp_path / "doc",
        "common": common,
    }


def test_original_copyright_common_text_and_actual_library_bytes_are_bound(bundle):
    result = licences.collect_linux_libraries(**bundle)
    assert result[0]["name"] == "Debian-libexample1"
    assert result[0]["version"] == "1.2-3"
    assert result[0]["libraries"][0]["sha256"] == licences.digest(
        bundle["runtime"] / "_internal/libexample.so.1"
    )
    assert {item["path"] for item in result[0]["licences"]} == {
        "system/libexample1/copyright",
        "system/common/GPL-3",
    }
    for item in result[0]["licences"]:
        assert licences.digest(bundle["notices"] / item["path"]) == item["sha256"]


@pytest.mark.parametrize(
    "missing", ["copyright", "common_text", "origin", "changed_bytes"]
)
def test_missing_or_wrong_provenance_refuses_native_package(bundle, missing):
    if missing == "copyright":
        (bundle["documentation"] / "libexample1/copyright").unlink()
    elif missing == "common_text":
        (bundle["common"] / "GPL-3").unlink()
    elif missing == "origin":
        bundle["sources"] = {}
    else:
        (bundle["runtime"] / "_internal/libexample.so.1").write_bytes(b"changed")
    with pytest.raises(RuntimeError):
        licences.collect_linux_libraries(**bundle)


@pytest.mark.parametrize("mutation", ["lost", "changed_notice", "changed_library"])
def test_coverage_gate_refuses_lost_or_changed_notice_and_library_bytes(
    bundle, mutation
):
    result = licences.collect_linux_libraries(**bundle)
    if mutation == "lost":
        result[0]["libraries"] = []
    elif mutation == "changed_notice":
        (bundle["notices"] / "system/libexample1/copyright").write_text("replacement")
    else:
        (bundle["runtime"] / "_internal/libexample.so.1").write_bytes(b"replacement")
    with pytest.raises(RuntimeError):
        licences.verify_linux_libraries(result, bundle["runtime"], bundle["notices"])


def test_publisher_rejects_unsafe_or_duplicated_notice_records(bundle):
    result = licences.collect_linux_libraries(**bundle)
    unsafe = copy.deepcopy(result)
    unsafe[0]["licences"][0]["path"] = "../unrelated"
    with pytest.raises(RuntimeError, match="invalid"):
        licences.library_records(unsafe)
    with pytest.raises(RuntimeError, match="duplicated"):
        licences.library_records([*result, *result])
