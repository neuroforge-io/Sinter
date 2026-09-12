"""Actual RKC compilation and HTTP interoperability with binary provenance; no AI calls."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from sinter import atlas


def binary_sha256(binary: Path) -> str:
    """Hash the executable without loading the entire file into memory."""
    digest = hashlib.sha256()
    with binary.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def binary_metadata(binary: Path) -> dict:
    """Record observed executable identity; absent build metadata stays unknown."""
    metadata = {'name': binary.name, 'sha256': binary_sha256(binary),
                'reported_version': None, 'go_build': None, 'warnings': []}
    try:
        version = subprocess.run([str(binary), '--version'], capture_output=True,
                                 text=True, errors='replace', timeout=10, check=False)
        if version.returncode == 0 and version.stdout.strip():
            metadata['reported_version'] = version.stdout.strip()[:200]
        else:
            metadata['warnings'].append('The executable did not report a version.')
    except (OSError, subprocess.SubprocessError):
        metadata['warnings'].append('The executable version could not be read.')
    go = shutil.which('go')
    if go is None:
        metadata['warnings'].append('Go is unavailable; embedded build revision was not inspected.')
        return metadata
    try:
        result = subprocess.run([go, 'version', '-m', str(binary)], capture_output=True,
                                text=True, errors='replace', timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        metadata['warnings'].append('Embedded Go build metadata could not be read.')
        return metadata
    if result.returncode != 0:
        metadata['warnings'].append('The executable has no readable Go build metadata.')
        return metadata
    build = {'evidence': 'embedded Go build metadata', 'go_version': None,
             'module': None, 'module_version': None, 'vcs_revision': None,
             'vcs_modified': None}
    for line in result.stdout.splitlines():
        columns = line.strip().split('\t')
        if len(columns) == 1:
            value = line.rpartition(': ')[2]
            if re.fullmatch(r'go\S{1,40}', value):
                build['go_version'] = value
        elif columns[0] == 'mod' and len(columns) >= 3:
            build['module'], build['module_version'] = columns[1:3]
        elif columns[0] == 'build':
            key, _, value = columns[1].partition('=')
            if key == 'vcs.revision' and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', value):
                build['vcs_revision'] = value
            elif key == 'vcs.modified' and value in {'true', 'false'}:
                build['vcs_modified'] = value == 'true'
    metadata['go_build'] = build
    if build['vcs_revision'] is None:
        metadata['warnings'].append('The embedded build metadata does not identify a source revision.')
    return metadata


def ci_reference(metadata: dict) -> dict:
    """Compare observed metadata with the CI checkout pin, never invent a match."""
    workflow = ROOT / '.github' / 'workflows' / 'ci.yml'
    try:
        match = re.search(r'repository:\s*neuroforge-io/RKC\s+ref:\s*([0-9a-f]{40})\b',
                          workflow.read_text(encoding='utf-8'))
    except (OSError, UnicodeError):
        match = None
    expected = match[1] if match else None
    observed = (metadata.get('go_build') or {}).get('vcs_revision')
    return {'expected_revision': expected, 'expectation_source': '.github/workflows/ci.yml',
            'observed_revision_matches': (observed == expected) if observed and expected else None,
            'notice': 'The digest identifies the tested executable. Version and revision are reported '
                      'by the executable and its embedded build metadata, not independently reproduced source provenance.'}


def main(argv: list[str] | None = None) -> None:
    """Run the real RKC interoperability gate using an explicit binary."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Build the pinned RKC revision used by .github/workflows/ci.yml first.',
    )
    parser.add_argument('binary', type=Path, help='Path to the compiled RKC executable.')
    args = parser.parse_args(argv)
    binary = args.binary.expanduser().resolve()
    if not binary.is_file():
        parser.error(f'RKC executable does not exist: {binary}. Build RKC and pass its executable path.')
    if not os.access(binary, os.X_OK):
        parser.error(f'RKC path is not executable: {binary}. Pass the compiled RKC binary.')
    try:
        run_check(binary)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'{parser.prog}: RKC integration failed: {exc}\n')


def run_check(binary: Path) -> None:
    """Compile and query actual RKC, retaining a receipt only after success."""
    metadata = binary_metadata(binary)
    files = [{'name':'garden.py', 'content':'def garden_budget():\n    """Garden budget is proposed; spending has not been approved."""\n    return 0\n'},
             {'name':'notes.md','content':'# Garden planning\nNo spending was approved. Request quotes before a decision.\n'}]
    generated = atlas.compile_collection(files, str(binary), True)
    assert generated['summary']['item_count'] > 0
    result = atlas.context(generated['document'], 'garden')
    assert result['items']
    with tempfile.TemporaryDirectory(prefix='sinter-rkc-real-') as folder:
        root=Path(folder)
        for row in files: (root/row['name']).write_text(row['content'], encoding='utf-8')
        subprocess.run([str(binary),'quickstart', str(root)], check=True, timeout=180)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        with (root/'server.log').open('w') as log:
            process = subprocess.Popen([str(binary), 'serve', '--dir', str(root/'.rkc'), '--addr', f'127.0.0.1:{port}'],
                                       stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            try:
                error=None; document=None
                for _ in range(30):
                    try:
                        document=atlas.retrieve(port, 'garden'); break
                    except ValueError as exc:
                        error=exc; time.sleep(.25)
                if document is None: raise RuntimeError('Actual RKC context failed: '+str(error))
                assert document['schema_version']=='rkc-context/v1'
                assert atlas.context(document, 'garden')['items']
                receipt={'schema':'sinter-rkc-test/v2','passed':True,
                         'tested_at':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                         'binary':metadata,'ci_reference':ci_reference(metadata),
                         'snapshot_id':document['snapshot_id'],'items':len(document['items']),
                         'checks':['selected-file compilation','bundle import','real RKC HTTP context','snapshot header and citation binding','bounded excerpt selection'],
                         'model_calls':0,'qualification_claim':False}
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    if binary_sha256(binary) != metadata['sha256']:
        raise ValueError('The RKC executable changed during the check; no new receipt was saved.')
    output=ROOT/'rkc-artifacts'; output.mkdir(exist_ok=True)
    (output/'compatibility.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__': main()
