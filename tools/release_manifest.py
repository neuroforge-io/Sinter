"""Fail a release unless all nine installed-app receipts match this checkout."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from sinter import __version__

EXPECTED = {('windows', arch) for arch in ('x64', 'x86', 'arm64')} | {('darwin', arch) for arch in ('x64', 'arm64')} | {('linux', arch) for arch in ('x64', 'x86', 'arm64', 'armv7')}


def assemble(output: Path, source: Path, commit: str):
    receipts = sorted(output.glob('*-test.json'))
    if len(receipts) != len(EXPECTED):
        raise ValueError('A required architecture receipt is missing or duplicated.')
    targets = set(); records = []
    for path in receipts:
        row = json.loads(path.read_text(encoding='utf-8'))
        system = row['system'].lower(); arch = row['target_arch']
        key = (system, arch)
        if key not in EXPECTED or key in targets:
            raise ValueError('Unexpected or duplicate installer target.')
        targets.add(key)
        if row.get('passed') is not True or row.get('frozen') is not True or row.get('version') != __version__ or row.get('source_commit') != commit:
            raise ValueError('An installer receipt does not match the release source.')
        name = row['installer']
        if Path(name).name != name or not name.startswith(f'Sinter-{__version__}-'):
            raise ValueError('Invalid installer filename.')
        package = output/name
        if hashlib.sha256(package.read_bytes()).hexdigest() != row['installer_sha256']:
            raise ValueError('An installer digest does not match its test receipt.')
        if not row.get('installer_test'):
            raise ValueError('Installed-app validation is missing.')
        records.append(row)
    if targets != EXPECTED:
        raise ValueError('Not all required installer targets passed.')
    if (source/'verified-commit.txt').read_text(encoding='utf-8').strip() != commit:
        raise ValueError('Source archive was tested at a different commit.')
    shutil.copy2(source/'sinter-source.zip', output/f'sinter-{__version__}-source.zip')
    shutil.copy2(source/'dist'/'sinter.pyz', output/f'sinter-{__version__}.pyz')
    (output/'build-manifest.json').write_text(json.dumps({'schema':'sinter-release/v1', 'version':__version__, 'source_commit':commit,
        'installer_targets':records, 'publisher_signed':False, 'speech_bundled':False, 'rkc_bundled':False}, indent=2), encoding='utf-8')
    checksums=[]
    for path in sorted(output.iterdir()):
        if path.is_file() and not path.name.endswith('.sha256') and path.name != 'SHA256SUMS.txt':
            checksums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
    (output/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n', encoding='ascii')
    print(f'Verified {len(records)} installed targets and source at {commit}')


if __name__ == '__main__':
    assemble(Path(sys.argv[1]), Path(sys.argv[2]), os.environ['GITHUB_SHA'])
