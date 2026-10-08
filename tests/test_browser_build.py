"""Check browser artifact identity independently of filesystem traversal order."""

import hashlib
import http.client
import importlib.util
import io
import json
import runpy
import sys
import urllib.error
from pathlib import Path

import pytest


def _load_builder():
    builder_path = Path(__file__).parents[1] / 'browser' / 'build.py'
    spec = importlib.util.spec_from_file_location(
        'sinter_browser_builder', builder_path,
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


@pytest.fixture
def vendor_build(tmp_path, monkeypatch):
    builder = _load_builder()
    source = tmp_path / 'source'
    (source / 'browser').mkdir(parents=True)
    contents = {
        'first.js': b'fictional first pinned asset',
        'last.wasm': b'fictional last pinned asset',
    }
    (source / 'browser/vendor-sha256.json').write_text(json.dumps({
        name: hashlib.sha256(content).hexdigest()
        for name, content in contents.items()
    }), encoding='utf-8')
    monkeypatch.setattr(builder, 'SOURCE', source)
    output = tmp_path / 'existing-output'
    (output / 'static').mkdir(parents=True)
    (output / 'index.html').write_bytes(b'previous complete browser application')
    (output / 'static/app.js').write_bytes(b'previous application script')
    return builder, output, contents


def _output_bytes(output):
    return {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob('*') if path.is_file()
    }


def _forbid_network(*args, **kwargs):
    raise AssertionError('An offline vendor cache must never use the network.')


def test_explicit_vendor_missing_asset_preserves_output_without_fallback(
    vendor_build, tmp_path, monkeypatch,
):
    builder, output, contents = vendor_build
    vendor = tmp_path / 'incomplete-cache'
    vendor.mkdir()
    (vendor / 'first.js').write_bytes(contents['first.js'])
    # Even a valid output cache must not replace the explicitly selected cache.
    (output / 'vendor').mkdir()
    (output / 'vendor/last.wasm').write_bytes(contents['last.wasm'])
    original = _output_bytes(output)
    monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)

    with pytest.raises(OSError) as error:
        builder.build(output, vendor)

    assert 'last.wasm' in str(error.value)
    assert str(vendor / 'last.wasm') in str(error.value)
    assert isinstance(error.value.__cause__, FileNotFoundError)
    assert _output_bytes(output) == original


def test_missing_explicit_vendor_does_not_create_output(
    vendor_build, tmp_path, monkeypatch,
):
    builder, _, _ = vendor_build
    output = tmp_path / 'uncreated-output'
    vendor = tmp_path / 'uncreated-vendor'
    monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)

    with pytest.raises(OSError, match='first.js'):
        builder.build(output, vendor)

    assert not output.exists()
    assert not vendor.exists()


@pytest.mark.parametrize('explicit', [False, True])
def test_invalid_last_vendor_asset_preserves_output_without_network(
    vendor_build, tmp_path, monkeypatch, explicit,
):
    builder, output, contents = vendor_build
    vendor = tmp_path / 'selected-cache' if explicit else output / 'vendor'
    vendor.mkdir()
    (vendor / 'first.js').write_bytes(contents['first.js'])
    invalid = b'corrupt runtime bytes'
    (vendor / 'last.wasm').write_bytes(invalid)
    original = _output_bytes(output)
    monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)

    with pytest.raises(ValueError) as error:
        builder.build(output, vendor if explicit else None)

    assert 'last.wasm' in str(error.value)
    assert str(vendor / 'last.wasm') in str(error.value)
    assert hashlib.sha256(contents['last.wasm']).hexdigest() in str(error.value)
    assert hashlib.sha256(invalid).hexdigest() in str(error.value)
    assert _output_bytes(output) == original


@pytest.mark.parametrize('failure', [
    urllib.error.URLError(ConnectionResetError(104, 'Connection reset by peer')),
    urllib.error.HTTPError(
        'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/last.wasm',
        404, 'Not Found', None, None,
    ),
])
def test_vendor_download_failure_names_asset_and_preserves_output(
    vendor_build, monkeypatch, failure,
):
    builder, output, contents = vendor_build
    calls = []
    original = _output_bytes(output)

    def download(url, timeout):
        calls.append((url, timeout))
        if url == builder.VENDOR_URL + 'first.js':
            return io.BytesIO(contents['first.js'])
        raise failure

    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)

    with pytest.raises(OSError) as error:
        builder.build(output)

    assert builder.VENDOR_URL + 'last.wasm' in str(error.value)
    assert str(failure) in str(error.value)
    assert 'No automatic retry' in str(error.value)
    assert error.value.__cause__ is failure
    assert calls == [
        (builder.VENDOR_URL + 'first.js', 120),
        (builder.VENDOR_URL + 'last.wasm', 120),
    ]
    assert _output_bytes(output) == original


def test_interrupted_vendor_body_is_not_retried_or_written(
    vendor_build, monkeypatch,
):
    builder, output, contents = vendor_build
    failure = http.client.IncompleteRead(b'partial', 12)
    original = _output_bytes(output)
    calls = []

    class InterruptedResponse(io.BytesIO):
        def read(self, size=-1):
            raise failure

    def download(url, timeout):
        calls.append(url)
        if url.endswith('first.js'):
            return io.BytesIO(contents['first.js'])
        return InterruptedResponse()

    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)

    with pytest.raises(OSError) as error:
        builder.build(output)

    assert error.value.__cause__ is failure
    assert builder.VENDOR_URL + 'last.wasm' in str(error.value)
    assert calls == [
        builder.VENDOR_URL + 'first.js', builder.VENDOR_URL + 'last.wasm',
    ]
    assert _output_bytes(output) == original


def test_downloaded_digest_mismatch_is_not_retried_or_written(
    vendor_build, monkeypatch,
):
    builder, output, contents = vendor_build
    calls = []
    original = _output_bytes(output)

    def download(url, timeout):
        calls.append(url)
        return io.BytesIO(
            contents['first.js'] if url.endswith('first.js') else b'wrong payload'
        )

    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)

    with pytest.raises(ValueError) as error:
        builder.build(output)

    assert builder.VENDOR_URL + 'last.wasm' in str(error.value)
    assert calls == [
        builder.VENDOR_URL + 'first.js', builder.VENDOR_URL + 'last.wasm',
    ]
    assert _output_bytes(output) == original


@pytest.mark.parametrize('explicit', [False, True])
def test_complete_verified_cache_is_admitted_offline(
    vendor_build, tmp_path, monkeypatch, explicit,
):
    builder, output, contents = vendor_build
    vendor = tmp_path / 'selected-cache' if explicit else output / 'vendor'
    vendor.mkdir()
    for name, content in contents.items():
        (vendor / name).write_bytes(content)
    original = _output_bytes(output)
    monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)

    assert builder._vendor_payloads(output, vendor if explicit else None) == contents
    assert _output_bytes(output) == original


def test_missing_default_cache_fetches_only_the_missing_pinned_asset(
    vendor_build, monkeypatch,
):
    builder, output, contents = vendor_build
    (output / 'vendor').mkdir()
    (output / 'vendor/first.js').write_bytes(contents['first.js'])
    calls = []
    original = _output_bytes(output)

    def download(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(contents['last.wasm'])

    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)

    assert builder._vendor_payloads(output, None) == contents
    assert calls == [(builder.VENDOR_URL + 'last.wasm', 120)]
    assert _output_bytes(output) == original


@pytest.mark.parametrize('explicit', [False, True])
def test_oversized_vendor_is_rejected_before_output_changes(
    vendor_build, tmp_path, monkeypatch, explicit,
):
    builder, output, contents = vendor_build
    monkeypatch.setattr(builder, 'VENDOR_MAX_BYTES', len(contents['first.js']))
    original = _output_bytes(output)
    if explicit:
        vendor = tmp_path / 'oversized-cache'
        vendor.mkdir()
        (vendor / 'first.js').write_bytes(contents['first.js'] + b'x')
        monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)
    else:
        vendor = None
        monkeypatch.setattr(
            builder.urllib.request, 'urlopen',
            lambda url, timeout: io.BytesIO(contents['first.js'] + b'x'),
        )

    with pytest.raises(ValueError, match="first.js.*exceeds"):
        builder.build(output, vendor)

    assert _output_bytes(output) == original


def test_cli_vendor_failure_reports_context_and_exit_one(
    tmp_path, monkeypatch, capsys,
):
    builder = _load_builder()
    output = tmp_path / 'uncreated-output'
    vendor = tmp_path / 'missing-cache'
    monkeypatch.setattr(builder.urllib.request, 'urlopen', _forbid_network)
    monkeypatch.setattr(sys, 'argv', [
        str(builder.__file__), str(output), '--vendor', str(vendor),
    ])

    with pytest.raises(SystemExit) as error:
        runpy.run_path(builder.__file__, run_name='__main__')

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert stderr.startswith('Browser build failed: ')
    assert str(vendor / 'pyodide-lock.json') in stderr
    assert 'Traceback' not in stderr
    assert not output.exists()


def test_browser_build_is_identical_when_source_traversal_is_reversed(
    tmp_path, monkeypatch,
):
    builder = _load_builder()
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
