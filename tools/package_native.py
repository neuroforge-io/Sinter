"""Build and install-test interpreter-bundled core packages on their target OS.

No publisher signing is claimed. ARMv7 emulation and x86 compatibility runs
are labelled explicitly. Account verification is bundled on supported crypto
targets; incompatible targets use --without-accounts. Speech and RKC are absent.
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


def collect_licences(notices, *, accounts=True):
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
    (notices / "bundled-dependencies.json").write_text(
        json.dumps(
            {
                "schema": "sinter-native-dependencies/v1",
                "packages": inventory,
                "account_auth_bundled": accounts,
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


def freezer_arguments(account_auth=True):
    """Share the exact runtime collection with isolated frozen-build validation."""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
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
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "faster_whisper",
        "--add-data",
        str(ROOT / "LICENSE") + os.pathsep + ".",
        "--add-data",
        str(ROOT / "NOTICE") + os.pathsep + ".",
        *account_bundle_arguments(account_auth),
    ]


def record_installed_receipt(receipt, installed, account_auth=True):
    """Keep auditable installed evidence and bind it to the frozen build."""
    identity = ("schema", "version", "system", "machine", "pointer_bits", "python")
    if (
        installed.get("passed") is not True
        or installed.get("frozen") is not True
        or any(installed.get(field) != receipt.get(field) for field in identity)
    ):
        raise RuntimeError("Installed runtime does not match the tested frozen build.")
    verify_account_receipt(installed, account_auth)
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
    args = parser.parse_args(argv)
    for module, label in [("PyInstaller", "PyInstaller"), ("certifi", "certifi")]:
        require_module(
            parser, module, label, "python -m pip install pyinstaller==6.22.2 certifi"
        )
    account_auth = not args.without_accounts
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
    cmd = freezer_arguments(account_auth)
    if sys.platform == "win32":
        cmd += ["--windowed", "--icon", str(ico)]
    elif sys.platform == "darwin":
        cmd += [
            "--windowed",
            "--icon",
            str(icns),
            "--osx-bundle-identifier",
            "io.neuroforge.sinter",
        ]
    run(*cmd, ROOT / "packaging" / "desktop_entry.py")
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
    dependencies = collect_licences(notices, accounts=account_auth)
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
    receipt.update(
        {
            "execution": args.execution,
            "target_arch": args.arch,
            "signed_by_publisher": False,
            "pyinstaller": importlib.metadata.version("pyinstaller"),
            "speech_bundled": False,
            "source_commit": os.environ.get("GITHUB_SHA", "local"),
            "bundled_dependencies": dependencies,
        }
    )
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
            record_installed_receipt(receipt, installed, account_auth)
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
            record_installed_receipt(receipt, installed, account_auth)
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
            "[Desktop Entry]\nType=Application\nName=Sinter\n"
            "Comment=Community workbench by NeuroForge\n"
            "Exec=/opt/neuroforge/sinter/Sinter\nIcon=sinter\n"
            "Terminal=false\nCategories=Office;Utility;\n",
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
            "Description: Local-first community workbench using the Fracture API\n"
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
            record_installed_receipt(receipt, installed, account_auth)
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
