"""Build and install-test interpreter-bundled core packages on their target OS.

No publisher signing is claimed. ARMv7 emulation and x86 compatibility runs
are labelled explicitly. Optional speech engines and RKC are not bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import plistlib
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
sys.path.insert(0, str(ROOT / 'src'))
from sinter import __version__
from tools._support import require_module


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def icon(folder: Path) -> tuple[Path, Path]:
    """Original pixel artwork, encoded without fonts or third-party image assets."""
    width = 256
    bitmap = ('01110', '11001', '11000', '01110', '00011', '10011', '01110')
    pixels = bytearray()
    for y in range(width):
        pixels.append(0)
        for x in range(width):
            colour = (255, 205 + y//16, 112, 255)
            gx, gy = (x-64)//26, (y-38)//26
            if 0 <= gx < 5 and 0 <= gy < 7 and bitmap[gy][gx] == '1':
                colour = (26, 32, 43, 255)
            pixels.extend(colour)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, width, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    ico, icns = folder/'sinter.ico', folder/'sinter.icns'
    ico.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png)
    icns.write_bytes(b'icns' + struct.pack('>I', len(png)+16) + b'ic08' + struct.pack('>I', len(png)+8) + png)
    return ico, icns


def collect_licences(notices):
    notices.mkdir(parents=True, exist_ok=True)
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, notices/name)
    for folder in (Path(sysconfig.get_path('stdlib')), Path(sys.base_prefix)):
        for name in ('LICENSE.txt', 'LICENSE'):
            if (folder/name).is_file():
                shutil.copy2(folder/name, notices/'Python-LICENSE.txt')
    if not (notices/'Python-LICENSE.txt').exists():
        raise RuntimeError('Python runtime licence could not be collected')
    for package, target in [('pyinstaller', 'PyInstaller-COPYING.txt'), ('certifi', 'certifi-LICENSE.txt')]:
        distribution = importlib.metadata.distribution(package)
        for entry in distribution.files or []:
            if entry.name.startswith('COPYING') or entry.name in {'LICENSE', 'LICENSE.txt'}:
                source = distribution.locate_file(entry)
                if source.is_file():
                    shutil.copy2(source, notices/target)
        if not (notices/target).exists():
            raise RuntimeError(f'{package} licence could not be collected')


def main(argv: list[str] | None = None) -> None:
    """Validate build setup before creating and install-testing native packages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', required=True, choices=['x64', 'x86', 'arm64', 'armv7'], help='Target architecture; requires a matching Python interpreter.')
    parser.add_argument('--execution', default='native', choices=['native', 'compatibility', 'emulated'], help='Record how the installed app is tested.')
    args = parser.parse_args(argv)
    for module, label in [('PyInstaller', 'PyInstaller'), ('certifi', 'certifi')]:
        require_module(parser, module, label, 'python -m pip install pyinstaller==6.22.2 certifi')
    os.chdir(ROOT)
    bits = struct.calcsize('P')*8
    assert bits == (32 if args.arch in {'x86', 'armv7'} else 64), 'Wrong Python architecture'
    if args.arch == 'arm64':
        assert platform.machine().lower() in {'arm64', 'aarch64'}, 'ARM64 Python is required'
    build, release = ROOT/'build', ROOT/'release'
    build.mkdir(exist_ok=True); release.mkdir(exist_ok=True)
    ico, icns = icon(build)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'Sinter',
           '--paths', str(ROOT/'src'), '--collect-submodules', 'sinter', '--collect-data', 'certifi', '--hidden-import', 'certifi',
           '--add-data', str(ROOT/'src'/'sinter'/'web') + os.pathsep + 'sinter/web',
           '--exclude-module', 'tkinter', '--exclude-module', 'faster_whisper',
           '--add-data', str(ROOT/'LICENSE')+os.pathsep+'.', '--add-data', str(ROOT/'NOTICE')+os.pathsep+'.']
    if sys.platform == 'win32':
        cmd += ['--windowed', '--icon', str(ico)]
    elif sys.platform == 'darwin':
        cmd += ['--windowed', '--icon', str(icns), '--osx-bundle-identifier', 'io.neuroforge.sinter']
    run(*cmd, ROOT/'packaging'/'desktop_entry.py')
    app = ROOT/'dist'/'Sinter'
    if sys.platform == 'darwin':
        app = ROOT/'dist'/'Sinter.app'
        binary, notices = app/'Contents'/'MacOS'/'Sinter', app/'Contents'/'Resources'/'licenses'
    else:
        binary, notices = app/('Sinter.exe' if sys.platform == 'win32' else 'Sinter'), app/'licenses'
    collect_licences(notices)
    if sys.platform == 'darwin':
        run('codesign', '--force', '--deep', '--sign', '-', app)
    prefix = f'Sinter-{__version__}-{platform.system().lower()}-{args.arch}'
    receipt_path = release/(prefix+'-test.json')
    try:
        run(binary, '--self-test', receipt_path, timeout=60)
    except subprocess.CalledProcessError:
        if receipt_path.exists():
            print(receipt_path.read_text(encoding='utf-8'), flush=True)
        raise
    receipt = json.loads(receipt_path.read_text())
    assert receipt['passed'] and receipt['frozen'] and receipt['pointer_bits'] == bits
    receipt.update({'execution': args.execution, 'target_arch': args.arch, 'signed_by_publisher': False,
                    'pyinstaller': importlib.metadata.version('pyinstaller'), 'speech_bundled': False,
                    'source_commit': os.environ.get('GITHUB_SHA', 'local')})
    if sys.platform == 'win32':
        iscc = shutil.which('ISCC')
        if not iscc:
            candidates = list(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')).glob('Inno Setup */ISCC.exe'))
            if not candidates:
                raise RuntimeError('Install Inno Setup before building the Windows installer')
            iscc = str(sorted(candidates)[-1])
        compiler_license = Path(iscc).parent/'license.txt'
        if compiler_license.is_file():
            shutil.copy2(compiler_license, notices/'Inno-Setup-LICENSE.txt')
        run(iscc, f'/DAppVersion={__version__}', f'/DTargetArch={args.arch}', ROOT/'packaging'/'windows.iss')
        installer = release/(prefix+'-setup.exe')
        with tempfile.TemporaryDirectory(prefix='sinter-install-') as temp:
            target = Path(temp)/'app'
            run(installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={target}', timeout=120)
            installed_receipt = Path(temp)/'installed.json'
            run(target/'Sinter.exe', '--self-test', installed_receipt, timeout=60)
            assert json.loads(installed_receipt.read_text())['passed']
            run(target/'unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', timeout=120)
            deadline = time.monotonic()+30
            while (target/'unins000.exe').exists() and time.monotonic() < deadline:
                time.sleep(.2)
            assert not (target/'Sinter.exe').exists(), 'Application remained after uninstall'
            assert not (target/'unins000.exe').exists(), 'Uninstaller did not finish cleanup'
        receipt['installer_test'] = 'installed, ran packaged HTTP/examples, uninstalled'
    elif sys.platform == 'darwin':
        stage = build/'pkg-root'
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(); shutil.copytree(app, stage/'Sinter.app', symlinks=True)
        installer = release/(prefix+'.pkg')
        components = build/'components.plist'
        run('pkgbuild', '--analyze', '--root', stage, components)
        definitions = plistlib.loads(components.read_bytes())
        for definition in definitions:
            definition['BundleIsRelocatable'] = False
        components.write_bytes(plistlib.dumps(definitions))
        run('pkgbuild', '--root', stage, '--component-plist', components, '--identifier', 'io.neuroforge.sinter',
            '--version', __version__, '--install-location', '/Applications', installer)
        run('sudo', 'installer', '-pkg', installer, '-target', '/')
        with tempfile.TemporaryDirectory() as temp:
            installed_receipt = Path(temp)/'installed.json'
            run('/Applications/Sinter.app/Contents/MacOS/Sinter', '--self-test', installed_receipt, timeout=60)
            assert json.loads(installed_receipt.read_text())['passed']
        receipt['installer_test'] = 'installed .pkg and ran installed application'
    else:
        debarch = {'x64':'amd64', 'arm64':'arm64', 'x86':'i386', 'armv7':'armhf'}[args.arch]
        stage = build/'deb-root'
        if stage.exists():
            shutil.rmtree(stage)
        target = stage/'opt'/'neuroforge'/'sinter'
        target.parent.mkdir(parents=True)
        shutil.copytree(app, target, symlinks=True)
        (stage/'usr'/'share'/'applications').mkdir(parents=True)
        icons = stage/'usr'/'share'/'icons'/'hicolor'/'scalable'/'apps'
        icons.mkdir(parents=True)
        shutil.copy2(ROOT/'src'/'sinter'/'web'/'icon.svg', icons/'sinter.svg')
        (stage/'usr'/'share'/'applications'/'sinter.desktop').write_text('[Desktop Entry]\nType=Application\nName=Sinter\nComment=Community workbench by NeuroForge\nExec=/opt/neuroforge/sinter/Sinter\nIcon=sinter\nTerminal=false\nCategories=Office;Utility;\n', encoding='utf-8')
        control = stage/'DEBIAN'; control.mkdir()
        libc = platform.libc_ver()[1]
        (control/'control').write_text(f'Package: sinter\nVersion: {__version__}\nArchitecture: {debarch}\nMaintainer: NeuroForge <support@neuroforge.io>\nDepends: libc6 (>= {libc}), zlib1g\nSection: utils\nPriority: optional\nDescription: Local-first community workbench using the Fracture API\n Bundled Python runtime. No model weights or proprietary model implementation.\n', encoding='utf-8')
        installer = release/(prefix+'.deb')
        run('dpkg-deb', '--root-owner-group', '--build', stage, installer)
        sudo = [] if os.geteuid() == 0 else ['sudo']
        run(*sudo, 'dpkg', '-i', installer)
        with tempfile.TemporaryDirectory() as temp:
            installed_receipt = Path(temp)/'installed.json'
            run('/opt/neuroforge/sinter/Sinter', '--self-test', installed_receipt, timeout=60)
            assert json.loads(installed_receipt.read_text())['passed']
        run(*sudo, 'dpkg', '-r', 'sinter')
        receipt['installer_test'] = 'installed .deb, ran installed HTTP/examples, removed package'
        receipt['glibc_minimum'] = libc
        shutil.make_archive(str(release/prefix), 'gztar', ROOT/'dist', 'Sinter')
    receipt['installer_sha256'] = hashlib.sha256(installer.read_bytes()).hexdigest()
    receipt['installer'] = installer.name
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    for path in release.iterdir():
        if path.is_file() and not path.name.endswith('.sha256'):
            (release/(path.name+'.sha256')).write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n', encoding='ascii')


if __name__ == '__main__':
    main()
