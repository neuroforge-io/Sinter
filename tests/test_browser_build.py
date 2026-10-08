"""Check browser artifact identity independently of filesystem traversal order."""

import hashlib
import importlib.util
import json
from pathlib import Path


def test_browser_build_is_identical_when_source_traversal_is_reversed(
    tmp_path, monkeypatch,
):
    builder_path = Path(__file__).parents[1] / 'browser' / 'build.py'
    spec = importlib.util.spec_from_file_location(
        'sinter_browser_builder', builder_path,
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = tmp_path / 'source'
    package = source / 'src' / 'sinter'
    web = package / 'web'
    browser = source / 'browser'
    web.mkdir(parents=True)
    browser.mkdir()
    sources = {
        'sinter/zeta.py': 'TITLE = "Fictional garden — volunteer handover"\n',
        'sinter/alpha.py': 'QUESTION = "Who has accepted the task?"\n',
        'sinter/web/offline-garden-casebook.json': '{"owner":"Unknown"}',
        'sinter/web/offline-garden-campaign.json': '{"date":"Unconfirmed"}',
    }
    for name, contents in sources.items():
        (source / 'src' / name).write_text(contents, encoding='utf-8')
    (package / 'local-only.txt').write_text('Do not bundle this file.')
    (web / 'index.html').write_text(
        '<html lang="en"><head></head><body><main id="content" tabindex="-1">'
        '<div id="view"></div></main></body></html>', encoding='utf-8',
    )
    (web / 'app.css').write_text('body { color: #123456; }')
    (web / 'app.js').write_text('export const title = "Garden";')
    for name in ('worker.js', 'main.js', 'browser.css', 'PYODIDE-LICENSE'):
        (browser / name).write_text('Fictional ' + name)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        (source / name).write_text('Fictional ' + name)
    vendor = tmp_path / 'vendor'
    vendor.mkdir()
    vendor_bytes = b'fictional offline runtime fixture'
    (vendor / 'runtime.js').write_bytes(vendor_bytes)
    (browser / 'vendor-sha256.json').write_text(json.dumps({
        'runtime.js': hashlib.sha256(vendor_bytes).hexdigest(),
    }))
    monkeypatch.setattr(builder, 'SOURCE', source)

    def forbid_network(*args, **kwargs):
        raise AssertionError('An offline builder fixture must never use the network.')

    monkeypatch.setattr(builder.urllib.request, 'urlopen', forbid_network)
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first_order = list(package.rglob('*'))
    builder.build(first, vendor)
    original_rglob = Path.rglob
    traversals = []

    def reversed_package_order(path, pattern):
        paths = list(original_rglob(path, pattern))
        if path == package:
            paths.reverse()
            traversals.append(paths.copy())
        return iter(paths)

    monkeypatch.setattr(Path, 'rglob', reversed_package_order)
    builder.build(second, vendor)

    assert traversals == [list(reversed(first_order))]
    assert first_order != traversals[0]
    assert json.loads(
        (first / 'python-files.json').read_text(encoding='utf-8')
    ) == sources
    assert json.loads(
        (second / 'python-files.json').read_text(encoding='utf-8')
    ) == sources
    assert (first / 'python-files.json').read_bytes() == (
        second / 'python-files.json'
    ).read_bytes()
    first_files = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob('*') if path.is_file()
    }
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob('*') if path.is_file()
    }
    assert first_files == second_files
    assert '—'.encode() in first_files['python-files.json']
    generated_text = (
        'python-files.json', 'build.json', 'asset-manifest.json', 'index.html',
    )
    for name in generated_text:
        assert b'\r' not in first_files[name]
    source_digest = hashlib.sha256(first_files['python-files.json']).hexdigest()
    assert json.loads(first_files['build.json'])['source_sha256'] == source_digest
    manifest = json.loads(first_files['asset-manifest.json'])
    assert set(manifest['files']) == set(first_files) - {'asset-manifest.json'}
    for name, record in manifest['files'].items():
        assert record == {
            'bytes': len(first_files[name]),
            'sha256': hashlib.sha256(first_files[name]).hexdigest(),
        }
