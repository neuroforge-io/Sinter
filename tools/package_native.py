"""Build and install-test interpreter-bundled core packages on their target OS.

No publisher signing is claimed. ARMv7 emulation and x86 compatibility runs
are labelled explicitly. Account verification is bundled on supported crypto
targets; incompatible targets use --without-accounts. Speech and RKC are absent.
Tcl/Tk is bundled by default; --without-native-window declares a CLI/browser-only
compatibility build. Resource self-tests do not qualify an interactive display.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from sinter import __version__  # noqa: E402
from tools._support import require_module  # noqa: E402
from tools.frozen_cli_smoke import qualify as qualify_cli  # noqa: E402
from tools.native_licences import (  # noqa: E402
    collect_linux_libraries,
    common_references,
    copy_notice,
    digest,
    library_records,
    package_owner,
)

AUTH_PACKAGES = ("PyJWT", "cryptography", "cffi", "pycparser") + (
    ("typing_extensions",) if sys.version_info < (3, 11) else ()
)
ACCOUNT_CHECK = "bundled ChatGPT identity verification"
RUNTIME_FIELDS = (
    "schema",
    "version",
    "system",
    "machine",
    "pointer_bits",
    "python",
    "frozen",
    "passed",
    "checks",
    "account_auth_bundled",
    "account_auth_dependencies",
    "native_window_bundled",
    "native_display_tested",
)


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def debian_package_version(version: str) -> str:
    """Keep Python pre-releases below the corresponding final Debian version."""
    parsed = re.fullmatch(
        r"(?P<release>[0-9]+(?:\.[0-9]+)*)"
        r"(?P<pre>(?:a|b|rc)[0-9]+)?"
        r"(?P<post>\.post[0-9]+)?"
        r"(?P<dev>\.dev[0-9]+)?",
        version,
    )
    if parsed is None:
        raise ValueError("Use a canonical release/pre/post/dev package version.")
    result = parsed["release"]
    if parsed["pre"]:
        result += "~" + parsed["pre"]
    if parsed["post"]:
        result += "+" + parsed["post"][1:]
    if parsed["dev"]:
        result += "~~" + parsed["dev"][1:]
    return result


def icon(folder: Path) -> tuple[Path, Path]:
    """Original pixel artwork, encoded without fonts or third-party image assets."""
    width = 256
    bitmap = ("01110", "11001", "11000", "01110", "00011", "10011", "01110")
    pixels = bytearray()
    for y in range(width):
        pixels.append(0)
        for x in range(width):
            colour = (255, 205 + y // 16, 112, 255)
            gx, gy = (x - 64) // 26, (y - 38) // 26
            if 0 <= gx < 5 and 0 <= gy < 7 and bitmap[gy][gx] == "1":
                colour = (26, 32, 43, 255)
            pixels.extend(colour)

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, width, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels))
        + chunk(b"IEND", b"")
    )
    ico, icns = folder / "sinter.ico", folder / "sinter.icns"
    ico.write_bytes(
        struct.pack("<HHH", 0, 1, 1)
        + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
        + png
    )
    icns.write_bytes(
        b"icns"
        + struct.pack(">I", len(png) + 16)
        + b"ic08"
        + struct.pack(">I", len(png) + 8)
        + png
    )
    return ico, icns


def native_window_build_info(info=None):
    """Require matching, collectible Tcl/Tk without opening a display."""
    problem = (
        "A matching Python tkinter/_tkinter and bundled Tcl/Tk runtime are required. "
        "Use an interpreter with Tcl/Tk, or explicitly choose --without-native-window "
        "for a CLI/browser-only package."
    )
    try:
        import _tkinter

        if info is None:
            from PyInstaller.utils.hooks.tcl_tk import tcltk_info

            info = tcltk_info
    except ImportError as exc:
        raise RuntimeError(problem) from exc
    if not info.available or info.is_macos_system_framework:
        raise RuntimeError(problem)
    if (
        tuple(map(int, _tkinter.TCL_VERSION.split("."))) != info.tcl_version
        or tuple(map(int, _tkinter.TK_VERSION.split("."))) != info.tk_version
    ):
        raise RuntimeError("Tcl/Tk versions do not match _tkinter. " + problem)
    required = (
        info.tkinter_extension_file,
        info.tcl_shared_library,
        info.tk_shared_library,
    )
    if any(not path or not Path(path).is_file() for path in required):
        raise RuntimeError(
            "Tcl/Tk extension or shared libraries are missing. " + problem
        )
    for path, entry in ((info.tcl_data_dir, "init.tcl"), (info.tk_data_dir, "tk.tcl")):
        if not path or not Path(path).joinpath(entry).is_file():
            raise RuntimeError("Tcl/Tk script resources are missing. " + problem)
    if not info.data_files:
        raise RuntimeError("Tcl/Tk script collection is empty. " + problem)
    return info


def windows_toolkit_notice(info, name: str, directory: Path) -> Path | None:
    """Recognize CPython's original combined notice, bound to this interpreter.

    PCbuild/regen.targets concatenates tcllicense.terms and tklicense.terms
    into LICENSE.txt; Windows installers do not retain those separate files.
    Preserve that entire original file, never reconstruct a notice from markers.
    """
    prefix = Path(sys.base_prefix).resolve()
    origins = (
        directory,
        Path(info.tkinter_extension_file),
        Path(info.tcl_shared_library),
        Path(info.tk_shared_library),
    )
    if any(not path.resolve().is_relative_to(prefix) for path in origins):
        return None
    notice = prefix / "LICENSE.txt"
    if not notice.is_file():
        return None
    text = " ".join(notice.read_text(encoding="utf-8").split())
    # These distinct upstream Tcl/Tk notices have the same grant/disclaimers,
    # but different copyright holders and restricted-rights clause numbers.
    holder = (
        "Corporation and other parties."
        if name == "Tcl"
        else "Corporation, Apple Inc. and other parties."
    )
    clause = "252.227-7014" if name == "Tcl" else "252.227-7013"
    markers = (
        "This software is copyrighted by the Regents of the University of "
        "California, Sun Microsystems, Inc., Scriptics Corporation, ActiveState "
        + holder,
        "The following terms apply to all files associated with the software "
        "unless explicitly disclaimed in individual files.",
        "The authors hereby grant permission to use, copy, modify, distribute, "
        "and license this software and its documentation for any purpose, provided",
        "this notice is included verbatim in any distributions.",
        "Modifications to this software may be copyrighted by their authors",
        "IN NO EVENT SHALL THE AUTHORS OR DISTRIBUTORS BE LIABLE TO ANY PARTY",
        "THE AUTHORS AND DISTRIBUTORS SPECIFICALLY DISCLAIM ANY WARRANTIES,",
        'IS PROVIDED ON AN "AS IS" BASIS,',
        "GOVERNMENT USE: If you are acquiring this software on behalf of the",
        clause + " (b) (3) of DFARs.",
        "terms specified in this license.",
    )
    # All markers must belong to one complete notice, not separate unrelated
    # sections or a passing mention of Tcl/Tk in Python's own licence.
    for section in text.split("This software is copyrighted by ")[1:]:
        section = "This software is copyrighted by " + section
        position = 0
        for marker in markers:
            position = section.find(marker, position)
            if position < 0:
                break
            position += len(marker)
        else:
            return notice
    return None


def collect_toolkit_licences(
    info,
    notices,
    runtime,
    *,
    documentation=Path("/usr/share/doc"),
    common=Path("/usr/share/common-licenses"),
):
    """Bind every collected script to its build origin and original notices."""
    data_root = (
        runtime / "Contents" / "Resources"
        if sys.platform == "darwin"
        else runtime / "_internal"
    )
    rows = []
    for name, directory, entry, version in (
        ("Tcl", info.tcl_data_dir, "init.tcl", info.tcl_version),
        ("Tk", info.tk_data_dir, "tk.tcl", info.tk_version),
    ):
        directory = Path(directory)
        if sys.platform.startswith("linux"):
            owner, _ = package_owner(directory / entry)
            copyright = documentation / owner / "copyright"
            if not copyright.is_file():
                raise RuntimeError(f"{name} original runtime licence is missing")
            sources = [copyright]
            sources.extend(
                common / reference
                for reference in common_references(
                    copyright.read_text(encoding="utf-8")
                )
            )
        else:
            candidates = [directory, directory.parent, directory.parent.parent]
            sources = [
                path
                for parent in candidates
                for filename in (name.lower() + "license.terms", "license.terms")
                if (path := parent / filename).is_file()
            ][:1]
            if not sources and sys.platform == "win32":
                combined = windows_toolkit_notice(info, name, directory)
                if combined is not None:
                    sources = [combined]
        if not sources:
            raise RuntimeError(
                f"{name} original runtime licence could not be collected"
            )
        licences = [
            copy_notice(source, notices / "toolkit" / name / source.name, notices)
            for source in sources
        ]
        scripts = []
        seen = set()
        for target, origin, kind in info.data_files:
            if not target or not Path(target).parts:
                raise RuntimeError("Bundled toolkit script path is invalid")
            toolkit = "Tk" if Path(target).parts[0] == "_tk_data" else "Tcl"
            if toolkit != name:
                continue
            origin, bundled = Path(origin), data_root / target
            if (
                kind != "DATA"
                or Path(target).is_absolute()
                or ".." in Path(target).parts
                or target in seen
                or not origin.is_file()
                or not bundled.is_file()
                or digest(origin) != digest(bundled)
            ):
                raise RuntimeError(
                    f"{name} bundled script origin is not proven: {target}"
                )
            seen.add(target)
            scripts.append(
                {
                    "path": bundled.relative_to(runtime).as_posix(),
                    "sha256": digest(bundled),
                    "origin": str(origin),
                }
            )
        if not scripts:
            raise RuntimeError(f"{name} bundled scripts are missing")
        rows.append(
            {
                "name": name,
                "version": ".".join(map(str, version)),
                "purpose": "bundled_native_toolkit",
                "licences": licences,
                "scripts": scripts,
            }
        )
    return rows


def collect_licences(notices, *, accounts=True, runtime=None, toolkit=None):
    notices.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, notices / name)
    for folder in (Path(sysconfig.get_path("stdlib")), Path(sys.base_prefix)):
        for name in ("LICENSE.txt", "LICENSE"):
            if (folder / name).is_file():
                shutil.copy2(folder / name, notices / "Python-LICENSE.txt")
    if not (notices / "Python-LICENSE.txt").exists():
        raise RuntimeError("Python runtime licence could not be collected")
    packages = [("pyinstaller", "bundled_bootloader"), ("certifi", "bundled_runtime")]
    if accounts:
        packages.extend((name, "bundled_runtime") for name in AUTH_PACKAGES)
    inventory = []
    for package, purpose in packages:
        distribution = importlib.metadata.distribution(package)
        package_licences = []
        for entry in distribution.files or []:
            if not entry.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
                continue
            source = distribution.locate_file(entry)
            if source.is_file():
                # Preserve every upstream licence variant, rather than overwriting
                # Apache/BSD notices into one ambiguously labelled file.
                parent = entry.parts[-2] if len(entry.parts) > 1 else "upstream"
                if parent in {".", ".."}:
                    parent = "upstream"
                target = notices / package / parent / entry.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                package_licences.append(
                    {
                        "path": target.relative_to(notices).as_posix(),
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    }
                )
        if not package_licences:
            raise RuntimeError(f"{package} licence could not be collected")
        inventory.append(
            {
                "name": package,
                "version": distribution.version,
                "purpose": purpose,
                "licences": package_licences,
            }
        )
    native = []
    if runtime is not None and sys.platform.startswith("linux"):
        native = collect_linux_libraries(runtime, notices)
        inventory.extend(native)
    if toolkit is not None:
        if runtime is None:
            raise RuntimeError("Toolkit notice collection requires a frozen runtime")
        inventory.extend(collect_toolkit_licences(toolkit, notices, runtime))
    (notices / "bundled-dependencies.json").write_text(
        json.dumps(
            {
                "schema": "sinter-native-dependencies/v1",
                "packages": inventory,
                "account_auth_bundled": accounts,
                "linux_shared_library_notices_verified": bool(native),
                "native_toolkit_notices_verified": toolkit is not None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return inventory


def account_bundle_arguments(enabled=True):
    """Make dynamic identity-verifier imports explicit to the freezer."""
    if not enabled:
        return [
            value
            for module in (
                "jwt",
                "cryptography",
                "cffi",
                "pycparser",
                "_cffi_backend",
                "typing_extensions",
            )
            for value in ("--exclude-module", module)
        ]
    return [
        "--collect-all",
        "jwt",
        "--collect-all",
        "cryptography",
        "--collect-all",
        "cffi",
        "--collect-all",
        "pycparser",
        "--hidden-import",
        "_cffi_backend",
        *(
            ["--hidden-import", "typing_extensions"]
            if "typing_extensions" in AUTH_PACKAGES
            else []
        ),
        *(value for name in AUTH_PACKAGES for value in ("--copy-metadata", name)),
    ]


def verify_account_receipt(receipt, enabled=True):
    """Do not infer frozen crypto usability from the build interpreter."""
    if receipt.get("account_auth_bundled") is not enabled:
        raise RuntimeError("Installed account capability does not match its build.")
    if not enabled and (
        receipt.get("account_auth_dependencies")
        or ACCOUNT_CHECK in receipt.get("checks", [])
    ):
        raise RuntimeError("Core-only build claimed account verification dependencies.")
    if enabled and ACCOUNT_CHECK not in receipt.get("checks", []):
        raise RuntimeError("Bundled ChatGPT identity verification did not pass.")
    if enabled:
        expected = {name: importlib.metadata.version(name) for name in AUTH_PACKAGES}
        if receipt.get("account_auth_dependencies") != expected:
            raise RuntimeError(
                "Bundled account dependency versions differ from the build."
            )


def native_window_bundle_arguments(enabled=True):
    """Use standard PyInstaller Tk hooks; compatibility builds omit both modules."""
    flag = "--hidden-import" if enabled else "--exclude-module"
    return [value for name in ("tkinter", "_tkinter") for value in (flag, name)]


def linux_native_window_library_arguments(enabled=True, *, resolve=None):
    """Collect Tk's XCB dependency even when the freezer treats it as system-only."""
    if not enabled or not sys.platform.startswith("linux"):
        return []
    if resolve is None:
        from PyInstaller.depend.bindepend import resolve_library_path

        resolve = resolve_library_path
    resolved = resolve("libxcb.so.1")
    library = Path(resolved) if resolved else None
    if library is None or not library.is_absolute() or not library.is_file():
        raise RuntimeError(
            "Linux native-window packaging requires build-host libxcb.so.1. "
            "Provide the normal libxcb1 package before building."
        )
    # Explicit binaries are traversed by PyInstaller; the existing Linux notice
    # collector then binds all copied dependencies to their original Debian bytes.
    return ["--add-binary", str(library) + os.pathsep + "."]


def freezer_arguments(account_auth=True, native_window=True):
    """Share the exact runtime collection with isolated frozen-build validation."""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        "Sinter",
        "--paths",
        str(ROOT / "src"),
        "--collect-submodules",
        "sinter",
        "--collect-data",
        "certifi",
        "--hidden-import",
        "certifi",
        "--add-data",
        str(ROOT / "src" / "sinter" / "web") + os.pathsep + "sinter/web",
        *native_window_bundle_arguments(native_window),
        *linux_native_window_library_arguments(native_window),
        "--exclude-module",
        "faster_whisper",
        "--exclude-module",
        "readline",
        "--add-data",
        str(ROOT / "LICENSE") + os.pathsep + ".",
        "--add-data",
        str(ROOT / "NOTICE") + os.pathsep + ".",
        *account_bundle_arguments(account_auth),
    ]


def verify_native_window_receipt(receipt, enabled=True):
    """A display-free package check proves resources, never GUI qualification."""
    if receipt.get("native_window_bundled") is not enabled:
        raise RuntimeError(
            "Installed native-window capability does not match its build."
        )
    if receipt.get("native_display_tested") is not False:
        raise RuntimeError(
            "Headless self-test must not claim native display qualification."
        )


def linux_desktop_entry(native_window=True):
    """Launch the presentation included in this Linux package."""
    command = "/opt/neuroforge/sinter/Sinter"
    if not native_window:
        command += " app --mode browser"
    return (
        "[Desktop Entry]\nType=Application\nName=Sinter\n"
        "Comment=Community workbench by NeuroForge\n"
        f"Exec={command}\nIcon=sinter\n"
        "Terminal=false\nCategories=Office;Utility;\n"
    )


def freeze_runtime(arguments, build, ico, icns):
    """Keep one console-capable executable, including inside the macOS app."""
    entry = ROOT / "packaging" / "desktop_entry.py"
    if sys.platform == "win32":
        run(*arguments, "--icon", ico, entry)
    elif sys.platform == "darwin":
        # PyInstaller's --windowed creates a .app but removes standard I/O.
        # Its documented BUNDLE spec target also accepts a console COLLECT.
        options = [
            arg for arg in arguments[3:] if arg not in {"--clean", "--noconfirm"}
        ]
        run(
            sys.executable,
            "-m",
            "PyInstaller.utils.cliutils.makespec",
            *options,
            "--specpath",
            build,
            entry,
        )
        spec = build / "Sinter.spec"
        with spec.open("a", encoding="utf-8") as stream:
            stream.write(
                "\napp = BUNDLE(coll, name='Sinter.app', "
                f"icon={str(icns)!r}, bundle_identifier='io.neuroforge.sinter', "
                f"version={__version__!r}, "
                "info_plist={'LSBackgroundOnly': False})\n"
            )
        run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec)
    else:
        run(*arguments, entry)


def record_installed_receipt(receipt, installed, account_auth=True, native_window=None):
    """Keep auditable installed evidence and bind it to the frozen build."""
    identity = ("schema", "version", "system", "machine", "pointer_bits", "python")
    if (
        installed.get("passed") is not True
        or installed.get("frozen") is not True
        or any(installed.get(field) != receipt.get(field) for field in identity)
    ):
        raise RuntimeError("Installed runtime does not match the tested frozen build.")
    verify_account_receipt(installed, account_auth)
    if native_window is not None:
        verify_native_window_receipt(installed, native_window)
    receipt["frozen_test"] = {
        field: receipt[field] for field in RUNTIME_FIELDS if field in receipt
    }
    receipt["installed_test"] = dict(installed)
    for field in RUNTIME_FIELDS:
        if field in installed:
            receipt[field] = installed[field]


def main(argv: list[str] | None = None) -> None:
    """Validate build setup before creating and install-testing native packages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arch",
        required=True,
        choices=["x64", "x86", "arm64", "armv7"],
        help="Target architecture; requires a matching Python interpreter.",
    )
    parser.add_argument(
        "--execution",
        default="native",
        choices=["native", "compatibility", "emulated"],
        help="Record how the installed app is tested.",
    )
    parser.add_argument(
        "--without-accounts",
        action="store_true",
        help=(
            "Omit ChatGPT sign-in on unsupported crypto targets. "
            "API-key connections and local tools remain available."
        ),
    )
    parser.add_argument(
        "--without-native-window",
        action="store_true",
        help="Build an explicit CLI/browser-only compatibility package without Tcl/Tk.",
    )
    args = parser.parse_args(argv)
    for module, label in [("PyInstaller", "PyInstaller"), ("certifi", "certifi")]:
        require_module(
            parser, module, label, "python -m pip install pyinstaller==6.22.2 certifi"
        )
    account_auth = not args.without_accounts
    native_window = not args.without_native_window
    toolkit = None
    if native_window:
        try:
            toolkit = native_window_build_info()
        except RuntimeError as exc:
            parser.error(str(exc))
    if account_auth:
        for module, label in [
            ("jwt", "PyJWT"),
            ("cryptography", "cryptography"),
            ("cffi", "cffi"),
            ("pycparser", "pycparser"),
        ] + (
            [("typing_extensions", "typing_extensions")]
            if "typing_extensions" in AUTH_PACKAGES
            else []
        ):
            require_module(parser, module, label, "python -m pip install '.[accounts]'")
    os.chdir(ROOT)
    bits = struct.calcsize("P") * 8
    assert bits == (32 if args.arch in {"x86", "armv7"} else 64), (
        "Wrong Python architecture"
    )
    if args.arch == "arm64":
        assert platform.machine().lower() in {"arm64", "aarch64"}, (
            "ARM64 Python is required"
        )
    build, release = ROOT / "build", ROOT / "release"
    build.mkdir(exist_ok=True)
    release.mkdir(exist_ok=True)
    ico, icns = icon(build)
    cmd = freezer_arguments(account_auth, native_window)
    freeze_runtime(cmd, build, ico, icns)
    app = ROOT / "dist" / "Sinter"
    if sys.platform == "darwin":
        app = ROOT / "dist" / "Sinter.app"
        binary, notices = (
            app / "Contents" / "MacOS" / "Sinter",
            app / "Contents" / "Resources" / "licenses",
        )
    else:
        binary, notices = (
            app / ("Sinter.exe" if sys.platform == "win32" else "Sinter"),
            app / "licenses",
        )
    dependencies = collect_licences(
        notices, accounts=account_auth, runtime=app, toolkit=toolkit
    )
    if sys.platform == "darwin":
        run("codesign", "--force", "--deep", "--sign", "-", app)
    prefix = f"Sinter-{__version__}-{platform.system().lower()}-{args.arch}"
    receipt_path = release / (prefix + "-test.json")
    try:
        run(binary, "--self-test", receipt_path, timeout=60)
    except subprocess.CalledProcessError:
        if receipt_path.exists():
            print(receipt_path.read_text(encoding="utf-8"), flush=True)
        raise
    receipt = json.loads(receipt_path.read_text())
    assert receipt["passed"] and receipt["frozen"] and receipt["pointer_bits"] == bits
    verify_account_receipt(receipt, account_auth)
    verify_native_window_receipt(receipt, native_window)
    receipt["frozen_cli_test"] = qualify_cli(binary)
    if receipt["frozen_cli_test"]["passed"] is not True:
        print(json.dumps(receipt["frozen_cli_test"], indent=2), flush=True)
        raise RuntimeError("The frozen shared CLI workflow did not pass.")
    receipt.update(
        {
            "execution": args.execution,
            "target_arch": args.arch,
            "signed_by_publisher": False,
            "pyinstaller": importlib.metadata.version("pyinstaller"),
            "speech_bundled": False,
            "native_window_requested": native_window,
            "native_toolkit_notices_verified": toolkit is not None,
            "console_capable": True,
            "source_commit": os.environ.get("GITHUB_SHA", "local"),
            "bundled_dependencies": dependencies,
            "linux_shared_library_notices_verified": (
                sys.platform.startswith("linux")
                and any(row.get("libraries") for row in dependencies)
            ),
        }
    )
    if sys.platform.startswith("linux"):
        receipt["native_shared_library_files"] = library_records(dependencies)
    if sys.platform == "win32":
        iscc = shutil.which("ISCC")
        if not iscc:
            candidates = list(
                Path(
                    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
                ).glob("Inno Setup */ISCC.exe")
            )
            if not candidates:
                raise RuntimeError(
                    "Install Inno Setup before building the Windows installer"
                )
            iscc = str(sorted(candidates)[-1])
        compiler_license = Path(iscc).parent / "license.txt"
        if compiler_license.is_file():
            shutil.copy2(compiler_license, notices / "Inno-Setup-LICENSE.txt")
        run(
            iscc,
            f"/DAppVersion={__version__}",
            f"/DTargetArch={args.arch}",
            ROOT / "packaging" / "windows.iss",
        )
        installer = release / (prefix + "-setup.exe")
        with tempfile.TemporaryDirectory(prefix="sinter-install-") as temp:
            target = Path(temp) / "app"
            run(
                installer,
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={target}",
                timeout=120,
            )
            installed_receipt = Path(temp) / "installed.json"
            run(target / "Sinter.exe", "--self-test", installed_receipt, timeout=60)
            installed = json.loads(installed_receipt.read_text())
            record_installed_receipt(receipt, installed, account_auth, native_window)
            run(
                target / "unins000.exe",
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                timeout=120,
            )
            deadline = time.monotonic() + 30
            while (target / "unins000.exe").exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            assert not (target / "Sinter.exe").exists(), (
                "Application remained after uninstall"
            )
            assert not (target / "unins000.exe").exists(), (
                "Uninstaller did not finish cleanup"
            )
        receipt["installer_test"] = "installed, ran packaged HTTP/examples, uninstalled"
    elif sys.platform == "darwin":
        stage = build / "pkg-root"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        shutil.copytree(app, stage / "Sinter.app", symlinks=True)
        installer = release / (prefix + ".pkg")
        components = build / "components.plist"
        run("pkgbuild", "--analyze", "--root", stage, components)
        definitions = plistlib.loads(components.read_bytes())
        for definition in definitions:
            definition["BundleIsRelocatable"] = False
        components.write_bytes(plistlib.dumps(definitions))
        run(
            "pkgbuild",
            "--root",
            stage,
            "--component-plist",
            components,
            "--identifier",
            "io.neuroforge.sinter",
            "--version",
            __version__,
            "--install-location",
            "/Applications",
            installer,
        )
        run("sudo", "installer", "-pkg", installer, "-target", "/")
        with tempfile.TemporaryDirectory() as temp:
            installed_receipt = Path(temp) / "installed.json"
            run(
                "/Applications/Sinter.app/Contents/MacOS/Sinter",
                "--self-test",
                installed_receipt,
                timeout=60,
            )
            installed = json.loads(installed_receipt.read_text())
            record_installed_receipt(receipt, installed, account_auth, native_window)
        receipt["installer_test"] = "installed .pkg and ran installed application"
    else:
        debarch = {"x64": "amd64", "arm64": "arm64", "x86": "i386", "armv7": "armhf"}[
            args.arch
        ]
        stage = build / "deb-root"
        if stage.exists():
            shutil.rmtree(stage)
        target = stage / "opt" / "neuroforge" / "sinter"
        target.parent.mkdir(parents=True)
        shutil.copytree(app, target, symlinks=True)
        (stage / "usr" / "share" / "applications").mkdir(parents=True)
        icons = stage / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        icons.mkdir(parents=True)
        shutil.copy2(ROOT / "src" / "sinter" / "web" / "icon.svg", icons / "sinter.svg")
        (stage / "usr" / "share" / "applications" / "sinter.desktop").write_text(
            linux_desktop_entry(native_window),
            encoding="utf-8",
        )
        control = stage / "DEBIAN"
        control.mkdir()
        libc = platform.libc_ver()[1]
        package_version = debian_package_version(__version__)
        (control / "control").write_text(
            f"Package: sinter\nVersion: {package_version}\nArchitecture: {debarch}\n"
            "Maintainer: NeuroForge <support@neuroforge.io>\n"
            f"Depends: libc6 (>= {libc}), zlib1g\nSection: utils\nPriority: optional\n"
            "Description: Local-first evidence and community workbench\n"
            " Bundled Python runtime. No model weights or proprietary model "
            "implementation.\n",
            encoding="utf-8",
        )
        installer = release / (prefix + ".deb")
        run("dpkg-deb", "--root-owner-group", "--build", stage, installer)
        installed_version = subprocess.check_output(
            ["dpkg-deb", "-f", str(installer), "Version"], text=True
        ).strip()
        assert installed_version == package_version, (
            "Debian installer control version did not match."
        )
        sudo = [] if os.geteuid() == 0 else ["sudo"]
        run(*sudo, "dpkg", "-i", installer)
        with tempfile.TemporaryDirectory() as temp:
            installed_receipt = Path(temp) / "installed.json"
            run(
                "/opt/neuroforge/sinter/Sinter",
                "--self-test",
                installed_receipt,
                timeout=60,
            )
            installed = json.loads(installed_receipt.read_text())
            record_installed_receipt(receipt, installed, account_auth, native_window)
        run(*sudo, "dpkg", "-r", "sinter")
        receipt["installer_test"] = (
            "installed .deb, ran installed HTTP/examples, removed package"
        )
        receipt["glibc_minimum"] = libc
        receipt["package_version"] = installed_version
        shutil.make_archive(str(release / prefix), "gztar", ROOT / "dist", "Sinter")
    receipt["installer_sha256"] = hashlib.sha256(installer.read_bytes()).hexdigest()
    receipt["installer"] = installer.name
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for path in release.iterdir():
        if path.is_file() and not path.name.endswith(".sha256"):
            (release / (path.name + ".sha256")).write_text(
                hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n",
                encoding="ascii",
            )


if __name__ == "__main__":
    main()
