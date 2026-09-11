"""Publication must refuse missing, altered or wrong-source installer artifacts."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from sinter import __version__

spec = importlib.util.spec_from_file_location('release_manifest', Path(__file__).parents[1]/'tools'/'release_manifest.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def artifacts(tmp_path):
    output=tmp_path/'out'; source=tmp_path/'source'
    output.mkdir(); (source/'dist').mkdir(parents=True)
    (source/'verified-commit.txt').write_text('fixture-commit\n')
    (source/'sinter-source.zip').write_bytes(b'fixture archive')
    (source/'dist'/'sinter.pyz').write_bytes(b'fixture zipapp')
    for system, arch in sorted(module.EXPECTED):
        name=f'Sinter-{__version__}-{system}-{arch}.fixture'
        (output/name).write_bytes(name.encode())
        row={'system':system, 'target_arch':arch, 'passed':True,'frozen':True,'version':__version__,
             'source_commit':'fixture-commit','installer':name,'installer_sha256':hashlib.sha256(name.encode()).hexdigest(),'installer_test':'fixture test'}
        (output/f'{system}-{arch}-test.json').write_text(json.dumps(row))
    return output, source


def test_complete_release_manifest(tmp_path):
    output, source = artifacts(tmp_path)
    module.assemble(output, source, 'fixture-commit')
    result=json.loads((output/'build-manifest.json').read_text())
    assert len(result['installer_targets']) == 9 and result['publisher_signed'] is False
    assert 'build-manifest.json' in (output/'SHA256SUMS.txt').read_text()


@pytest.mark.parametrize('mutation', ['missing', 'changed_package', 'wrong_source', 'failed', 'wrong_source_archive'])
def test_release_rejects_invalid_receipts(tmp_path, mutation):
    output, source = artifacts(tmp_path)
    path=next(output.glob('*-test.json')); row=json.loads(path.read_text())
    if mutation=='missing': path.unlink()
    elif mutation=='changed_package': (output/row['installer']).write_bytes(b'changed')
    elif mutation=='wrong_source': row['source_commit']='other'; path.write_text(json.dumps(row))
    elif mutation=='failed': row['passed']=False; path.write_text(json.dumps(row))
    else: (source/'verified-commit.txt').write_text('other')
    with pytest.raises(ValueError): module.assemble(output, source, 'fixture-commit')
    assert not (output/'build-manifest.json').exists()
