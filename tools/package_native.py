"""Build and install-test an architecture-specific, interpreter-bundled core app.

Run on the target OS with PyInstaller 6.22.2. No cross-build is represented as a
native run. Linux 32-bit CI uses a declared container/emulator. Signing requires
publisher credentials and is never fabricated. Runtime models are not bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sinter import __version__


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def icon(folder: Path) -> tuple[Path, Path]:
    """Original pixel artwork encoded using the standard library, not font assets."""
    width = 256
    bitmap = ('01110', '11001', '11000', '01110', '00011', '10011', '01110')
    pixels = bytearray()
    for y in range(width):
        pixels.append(0)
        for x in range(width):
            c = (255, 205 + y//16, 112, 255)
            gx, gy = (x-64)//26, (y-38)//26
            if 0 <= gx < 5 and 0 <= gy < 7 and bitmap[gy][gx] == '1':
                c = (26, 32, 43, 255)
            pixels.extend(c)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, width, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    ico = folder / 'sinter.ico'; icns = folder / 'sinter.icns'
    ico.write_bytes(struct.pack('<HHH', 0, 1, 1) + struct.pack('<BBBBHHII', 0, 0, 0, 0, 1, 32, len(png), 22) + png)
    icns.write_bytes(b'icns' + struct.pack('>I', len(png)+16) + b'ic08' + struct.pack('>I', len(png)+8) + png)
    return ico, icns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', required=True, choices=['x64', 'x86', 'arm64', 'armv7'])
    parser.add_argument('--execution', default='native', choices=['native', 'compatibility', 'emulated'])
    args = parser.parse_args()
    os.chdir(ROOT)
    bits = struct.calcsize('P')*8
    assert bits == (32 if args.arch in {'x86', 'armv7'} else 64), 'Wrong Python architecture'
    machine = platform.machine().lower()
    if args.arch == 'arm64':
        assert machine in {'arm64', 'aarch64'}, 'An ARM64 Python interpreter is required'
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
    cmd += [str(ROOT/'packaging'/'desktop_entry.py')]
    run(*cmd)
    app = ROOT/'dist'/'Sinter'
    if sys.platform == 'darwin':
        app = ROOT/'dist'/'Sinter.app'
        binary = app/'Contents'/'MacOS'/'Sinter'
        notices = app/'Contents'/'Resources'/'licenses'
    else:
        binary = app/('Sinter.exe' if sys.platform == 'win32' else 'Sinter')
        notices = app/'licenses'
    notices.mkdir(parents=True, exist_ok=True)
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'):
        if (ROOT/name).exists():
            shutil.copy2(ROOT/name, notices/name)
    for folder in (Path(sysconfig.get_path('stdlib')), Path(sys.base_prefix)):
        for name in ('LICENSE.txt', 'LICENSE'):
            if (folder/name).is_file():
                shutil.copy2(folder/name, notices/'Python-LICENSE.txt')
    if not (notices/'Python-LICENSE.txt').exists():
        raise RuntimeError('Python runtime licence could not be collected')
    import PyInstaller
    for name in ('COPYING.txt', 'COPYING'):
        candidates = [Path(PyInstaller.__file__).parent/name, Path(PyInstaller.__file__).parent.parent/name]
        for path in candidates:
            if path.is_file():
                shutil.copy2(path, notices/'PyInstaller-COPYING.txt')
    for entry in importlib.metadata.files('pyinstaller') or []:
        if entry.name.startswith('COPYING'):
            path = importlib.metadata.distribution('pyinstaller').locate_file(entry)
            if path.is_file():
                shutil.copy2(path, notices/'PyInstaller-COPYING.txt')
    if not (notices/'PyInstaller-COPYING.txt').exists():
        raise RuntimeError('PyInstaller distribution licence could not be collected')
    for entry in importlib.metadata.files('certifi') or []:
        if entry.name in {'LICENSE', 'LICENSE.txt'}:
            shutil.copy2(importlib.metadata.distribution('certifi').locate_file(entry), notices/'certifi-LICENSE.txt')
    if sys.platform == 'darwin':
        run('codesign', '--force', '--deep', '--sign', '-', str(app))
    prefix = f'Sinter-{__version__}-{platform.system().lower()}-{args.arch}'
    receipt_path = release/(prefix+'-test.json')
    try:
        run(binary, '--self-test', receipt_path, timeout=60)
    except subprocess.CalledProcessError:
        if receipt_path.exists():
            print(receipt_path.read_text(encoding='utf-8'))
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
        run(iscc, f'/DAppVersion={__version__}', f'/DTargetArch={args.arch}', ROOT/'packaging'/'windows.iss')
        installer = release/(prefix+'-setup.exe')
        with tempfile.TemporaryDirectory(prefix='sinter-install-') as temp:
            target = Path(temp)/'app'
            run(installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={target}', timeout=120)
            installed_receipt = Path(temp)/'installed.json'
            run(target/'Sinter.exe', '--self-test', installed_receipt, timeout=60)
            assert json.loads(installed_receipt.read_text())['passed']
            run(target/'unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', timeout=120)
            assert not (target/'Sinter.exe').exists()
        receipt['installer_test'] = 'installed, ran packaged HTTP/examples, uninstalled'
    elif sys.platform == 'darwin':
        stage = build/'pkg-root'
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(); shutil.copytree(app, stage/'Sinter.app', symlinks=True)
        installer = release/(prefix+'.pkg')
        run('pkgbuild', '--root', stage, '--identifier', 'io.neuroforge.sinter', '--version', __version__,
            '--install-location', '/Applications', installer)
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
        (stage/'usr'/'share'/'icons'/'hicolor'/'scalable'/'apps').mkdir(parents=True)
        shutil.copy2(ROOT/'src'/'sinter'/'web'/'icon.svg', stage/'usr'/'share'/'icons'/'hicolor'/'scalable'/'apps'/'sinter.svg')
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
