"""Prove the provenance and notices of shared libraries copied on Debian/Linux."""

from __future__ import annotations

import hashlib
import platform
import posixpath
import re
import shutil
import subprocess
import sysconfig
import tarfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def common_references(text: str) -> list[str]:
    return sorted(
        {
            name.rstrip(".")
            for name in re.findall(
                r"/usr/share/common-licenses/([A-Za-z0-9.+_-]+)", text
            )
        }
    )


def library_records(inventory: list[dict]) -> dict[str, str]:
    """Validate portable licence records without reading build-host paths."""
    recorded = {}
    for row in inventory:
        if not isinstance(row, dict) or row.get("purpose") != "bundled_shared_library":
            continue
        if (
            not isinstance(row.get("version"), str)
            or not row["version"]
            or not isinstance(row.get("licences"), list)
            or not row["licences"]
            or not isinstance(row.get("libraries"), list)
            or not row["libraries"]
        ):
            raise RuntimeError("Shared-library versions or notices are missing.")
        for item in [*row["licences"], *row["libraries"]]:
            path = item.get("path", "") if isinstance(item, dict) else ""
            sha = item.get("sha256", "") if isinstance(item, dict) else ""
            if (
                not isinstance(path, str)
                or not path
                or "\\" in path
                or ":" in path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
                or not isinstance(sha, str)
                or not re.fullmatch("[0-9a-f]{64}", sha)
            ):
                raise RuntimeError("Shared-library notice provenance is invalid.")
        name = row.get("name", "")
        licence_paths = {item["path"] for item in row["licences"]}
        required = (
            "system/" + name.removeprefix("Debian-") + "/copyright"
            if isinstance(name, str) and name.startswith("Debian-")
            else "Python-LICENSE.txt"
            if name == "Python-shared-runtime"
            else None
        )
        if required is None or required not in licence_paths:
            raise RuntimeError("Original shared-library copyright is missing.")
        for item in row["libraries"]:
            if not item["path"].startswith("_internal/") or item["path"] in recorded:
                raise RuntimeError(
                    "Shared-library provenance is duplicated or invalid."
                )
            recorded[item["path"]] = item["sha256"]
    if not recorded:
        raise RuntimeError("Bundled shared-library notice coverage is missing.")
    return recorded


def linker_sources() -> dict[str, list[Path]]:
    listing = subprocess.check_output(["ldconfig", "-p"], text=True)
    result: dict[str, list[Path]] = {}
    for line in listing.splitlines():
        match = re.match(r"\s+(\S+)\s.*=>\s(/.+)$", line)
        if match:
            result.setdefault(match[1], []).append(Path(match[2]))
    return result


def package_owner(path: Path) -> tuple[str, str]:
    for candidate in dict.fromkeys((path, path.resolve())):
        found = subprocess.run(
            ["dpkg-query", "-S", str(candidate)],
            capture_output=True,
            text=True,
            check=False,
        )
        if found.returncode == 0:
            owners = {row.rsplit(": ", 1)[0] for row in found.stdout.splitlines()}
            if len(owners) == 1:
                owner = owners.pop()
                name = owner.split(":")[0]
                if re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", name):
                    version = subprocess.check_output(
                        ["dpkg-query", "-W", "-f=${Version}", owner],
                        text=True,
                    ).strip()
                    return name, version
    raise RuntimeError(f"Bundled library owner is not proven: {path.name}")


def copy_notice(source: Path, target: Path, notices: Path) -> dict:
    if not source.is_file():
        raise RuntimeError(f"Required runtime notice is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"path": target.relative_to(notices).as_posix(), "sha256": digest(target)}


def collect_linux_libraries(
    runtime: Path,
    notices: Path,
    *,
    sources: dict[str, list[Path]] | None = None,
    documentation: Path = Path("/usr/share/doc"),
    common: Path = Path("/usr/share/common-licenses"),
) -> list[dict]:
    """Fail rather than bundle an untracked library without its original notice."""
    libraries = sorted((runtime / "_internal").rglob("lib*.so*"))
    libraries = [path for path in libraries if path.is_file()]
    if not libraries:
        raise RuntimeError("No bundled Linux shared-library inventory was found.")
    sources = linker_sources() if sources is None else sources
    groups: dict[str, dict] = {}
    for library in libraries:
        candidates = sources.get(library.name, [])
        python_library = library.name.startswith("libpython")
        if python_library:
            libdir = sysconfig.get_config_var("LIBDIR")
            if libdir:
                candidates = [*candidates, Path(libdir) / library.name]
        origin = next(
            (
                path
                for path in candidates
                if path.is_file() and digest(path) == digest(library)
            ),
            None,
        )
        if origin is None:
            raise RuntimeError(
                f"Bundled library bytes do not match a known origin: {library.name}"
            )
        if python_library:
            name, version = "Python-shared-runtime", platform.python_version()
            if name not in groups:
                python_notice = notices / "Python-LICENSE.txt"
                if not python_notice.is_file():
                    raise RuntimeError("Python shared-runtime licence is missing.")
                groups[name] = {
                    "name": name,
                    "version": version,
                    "purpose": "bundled_shared_library",
                    "licences": [
                        {"path": "Python-LICENSE.txt", "sha256": digest(python_notice)}
                    ],
                    "libraries": [],
                }
        else:
            package, version = package_owner(origin)
            name = "Debian-" + package
            if name not in groups:
                copyright = documentation / package / "copyright"
                licence = copy_notice(
                    copyright, notices / "system" / package / "copyright", notices
                )
                references = common_references(copyright.read_text(encoding="utf-8"))
                texts = [licence]
                for referenced in references:
                    texts.append(
                        copy_notice(
                            common / referenced,
                            notices / "system" / "common" / referenced,
                            notices,
                        )
                    )
                groups[name] = {
                    "name": name,
                    "version": version,
                    "purpose": "bundled_shared_library",
                    "licences": texts,
                    "libraries": [],
                }
        groups[name]["libraries"].append(
            {
                "path": library.relative_to(runtime).as_posix(),
                "sha256": digest(library),
                "origin": str(origin),
            }
        )
    result = [groups[name] for name in sorted(groups)]
    verify_linux_libraries(result, runtime, notices)
    return result


def verify_linux_libraries(inventory: list[dict], runtime: Path, notices: Path):
    """Compare declared coverage with actual copied library and notice bytes."""
    required = {
        path.relative_to(runtime).as_posix(): digest(path)
        for path in (runtime / "_internal").rglob("lib*.so*")
        if path.is_file()
    }
    recorded = library_records(inventory)
    for row in inventory:
        if not row.get("licences"):
            raise RuntimeError("Shared-library notices are missing.")
        for licence in row["licences"]:
            if digest(notices / licence["path"]) != licence["sha256"]:
                raise RuntimeError("Shared-library notice bytes have changed.")
    if not required or recorded != required:
        raise RuntimeError("Bundled shared-library notice coverage is incomplete.")


def verify_debian_archive(installer: Path, inventory: list[dict]):
    """Independently compare the installer payload with declared notice coverage."""
    declared = library_records(inventory)
    expected_notices = {}
    for row in inventory:
        for licence in row.get("licences", []):
            path = "licenses/" + licence["path"]
            if path in expected_notices and expected_notices[path] != licence["sha256"]:
                raise RuntimeError("Conflicting native notice digests.")
            expected_notices[path] = licence["sha256"]
    if installer.suffix != ".deb":
        raise RuntimeError("Linux qualification requires an actual Debian installer.")
    prefix = "opt/neuroforge/sinter/"
    digests, links, actual_libraries, copyrights = {}, {}, set(), {}
    process = subprocess.Popen(
        ["dpkg-deb", "--fsys-tarfile", str(installer)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = member.name.removeprefix("./")
                if not name.startswith(prefix):
                    continue
                relative = name.removeprefix(prefix)
                if ".." in Path(relative).parts or Path(relative).is_absolute():
                    raise RuntimeError("Invalid native archive path.")
                library = (
                    relative.startswith("_internal/")
                    and Path(relative).name.startswith("lib")
                    and ".so" in Path(relative).name
                )
                if not library and not relative.startswith("licenses/"):
                    continue
                if member.isfile():
                    if member.size > 64 * 1024 * 1024:
                        raise RuntimeError(
                            "Native library or notice exceeds its bound."
                        )
                    content = archive.extractfile(member)
                    sha = hashlib.sha256()
                    copyright_text = (
                        bytearray()
                        if relative.startswith("licenses/system/")
                        and relative.endswith("/copyright")
                        else None
                    )
                    if copyright_text is not None and member.size > 1024 * 1024:
                        raise RuntimeError("Native copyright exceeds its text bound.")
                    while chunk := content.read(1024 * 1024):
                        sha.update(chunk)
                        if copyright_text is not None:
                            copyright_text.extend(chunk)
                    digests[relative] = sha.hexdigest()
                    if copyright_text is not None:
                        copyrights[relative] = copyright_text.decode("utf-8")
                elif member.issym():
                    links[relative] = posixpath.normpath(
                        posixpath.join(posixpath.dirname(relative), member.linkname)
                    )
                elif member.islnk():
                    links[relative] = member.linkname.removeprefix("./").removeprefix(
                        prefix
                    )
                else:
                    continue
                if library:
                    actual_libraries.add(relative)
        if process.wait(timeout=20) != 0:
            raise RuntimeError("Debian installer payload could not be inspected.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)

    def payload_digest(path):
        visited = set()
        while path in links:
            if path in visited or ".." in Path(path).parts or Path(path).is_absolute():
                raise RuntimeError("Native archive link is invalid or circular.")
            visited.add(path)
            path = links[path]
        return digests.get(path)

    if actual_libraries != set(declared):
        raise RuntimeError("Actual installer library coverage does not match.")
    for path, sha in {**declared, **expected_notices}.items():
        if payload_digest(path) != sha:
            raise RuntimeError("Actual installer library or notice bytes do not match.")
    for text in copyrights.values():
        for referenced in common_references(text):
            path = "licenses/system/common/" + referenced
            if (
                path not in expected_notices
                or payload_digest(path) != expected_notices[path]
            ):
                raise RuntimeError("Actual installer referenced licence is missing.")
