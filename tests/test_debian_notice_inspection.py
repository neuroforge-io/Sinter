"""Publisher proof reads actual Debian payload bytes, independent of receipt maps."""

from __future__ import annotations

import copy
import shutil
import subprocess

import pytest

from tools import native_licences as licences


@pytest.fixture
def payload(tmp_path, monkeypatch):
    if not shutil.which("dpkg-deb"):
        pytest.skip("Actual Debian archive tooling is unavailable.")
    stage = tmp_path / "stage"
    runtime = stage / "opt/neuroforge/sinter"
    internal = runtime / "_internal"
    internal.mkdir(parents=True)
    origins = tmp_path / "origins"
    origins.mkdir()
    sources = {}
    for name in ("libfirst.so.1", "libsecond.so.1"):
        path = origins / name
        path.write_bytes(name.encode())
        (internal / name).write_bytes(path.read_bytes())
        sources[name] = [path]
    docs = tmp_path / "docs"
    copyright = docs / "libexample1/copyright"
    copyright.parent.mkdir(parents=True)
    copyright.write_text(
        "Copyright Original Authors. Permission notice.\n"
        "The full licence is /usr/share/common-licenses/GPL-3.\n"
    )
    common = tmp_path / "common"
    common.mkdir()
    (common / "GPL-3").write_text("Original full licence text.")
    monkeypatch.setattr(
        licences, "package_owner", lambda path: ("libexample1", "1.2-3")
    )
    inventory = licences.collect_linux_libraries(
        runtime,
        runtime / "licenses",
        sources=sources,
        documentation=docs,
        common=common,
    )
    control = stage / "DEBIAN/control"
    control.parent.mkdir()
    control.write_text(
        "Package: sinter\nVersion: 0.5.4~rc1\nArchitecture: amd64\n"
        "Maintainer: Fixture <fixture@example.invalid>\nDescription: Fixture\n"
    )
    return stage, runtime, inventory, tmp_path / "candidate.deb"


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "notice_bytes",
        "library_bytes",
        "undeclared_library",
        "removed_record",
        "missing_referenced_text",
    ],
)
def test_publisher_checks_archive_after_receipt_maps_have_been_changed(
    payload, mutation
):
    stage, runtime, inventory, installer = payload
    inventory = copy.deepcopy(inventory)
    if mutation == "notice_bytes":
        (runtime / "licenses/system/libexample1/copyright").write_text("Replacement")
    elif mutation == "library_bytes":
        (runtime / "_internal/libfirst.so.1").write_bytes(b"replacement")
    elif mutation == "undeclared_library":
        (runtime / "_internal/libuntracked.so.1").write_bytes(b"untracked")
    elif mutation == "removed_record":
        inventory[0]["libraries"].pop()
    elif mutation == "missing_referenced_text":
        (runtime / "licenses/system/common/GPL-3").unlink()
        inventory[0]["licences"] = [
            item
            for item in inventory[0]["licences"]
            if item["path"] != "system/common/GPL-3"
        ]
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "--build", str(stage), str(installer)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    if mutation == "none":
        licences.verify_debian_archive(installer, inventory)
    else:
        with pytest.raises(RuntimeError, match="Actual installer"):
            licences.verify_debian_archive(installer, inventory)
