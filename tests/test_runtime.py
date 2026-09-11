"""Real-loopback HTTP, persistence, jobs and packaging regression checks."""
import io
import json
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import __version__, client
from sinter.jobs import Job, Jobs
from sinter.server import make_server
from sinter.store import Store, calendar
from sinter.workbench import example, run


@pytest.fixture
def server(tmp_path):
    instance = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown(); instance.app.close(); instance.server_close(); thread.join(timeout=5)


def request(server, path='/', method='GET', body=None, headers=None):
    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def post(server, path, payload, token=True):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Sinter-Token'] = server.app.token
    return request(server, path, 'POST', json.dumps(payload), headers)


def test_modular_entrypoint_and_security_headers(server):
    code, headers, body = request(server)
    assert code == 200 and b'/static/app.js' in body and b'id="view"' in body
    assert 'unsafe-inline' not in headers['Content-Security-Policy']
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['X-Frame-Options'] == 'DENY'
    assert 'Access-Control-Allow-Origin' not in headers
    assert request(server, '/static/app.js')[0] == 200
    assert request(server, '/static/icon.svg')[0] == 200
    assert request(server, '/', 'HEAD')[2] == b''


@pytest.mark.parametrize('headers', [{'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_host_origin_and_fetch_site_denied(server, headers):
    assert request(server, '/api/session', headers=headers)[0] == 403


@pytest.mark.parametrize('path', ['/static/../client.py', '/static/%2e%2e%2fclient.py', '/static/..%5cclient.py', '/static/.env', '/static/%252e%252e%252fclient.py'])
def test_static_traversal_denied(server, path):
    assert request(server, path)[0] == 404


def test_write_requires_launch_token(server):
    assert post(server, '/api/workbench', example('brief'), token=False)[0] == 403
    assert post(server, '/api/workbench', example('brief'))[0] == 202


@pytest.mark.parametrize('body', ['{bad', '[]', '{"value":NaN}', '{}'])
def test_invalid_requests_do_not_crash_server(server, body):
    code, _, raw = request(server, '/api/screen', 'POST', body, {'Content-Type': 'application/json', 'X-Sinter-Token': server.app.token})
    assert code in {200, 400}
    assert isinstance(json.loads(raw), dict)
    assert request(server, '/api/session')[0] == 200


def test_health_reports_failure_not_success(server):
    with patch.object(client, 'health_check', return_value=(False, 'Fixture offline')):
        code, _, raw = request(server, '/api/health')
    assert code == 503 and json.loads(raw)['ok'] is False


def test_stream_failure_never_sends_done(server):
    def broken(*args, **kwargs):
        yield 'partial'
        raise client.APIError('Fixture upstream failure')
    with patch.object(client, 'chat_stream', side_effect=broken):
        code, _, raw = post(server, '/api/chat/stream', {'messages': [{'role': 'user', 'content': 'hello'}]})
    assert code == 200 and b'partial' in raw and b'"type": "error"' in raw
    assert b'[DONE]' not in raw


def test_reports_persist_and_delete(tmp_path):
    store = Store(tmp_path)
    report = run(example('brief'))
    identifier = store.save_report(report)
    reopened = Store(tmp_path)
    assert reopened.report(identifier) == report
    assert reopened.reports()[0]['id'] == identifier
    reopened.delete_report(identifier)
    with pytest.raises(KeyError): reopened.report(identifier)


def test_watch_lease_is_exclusive(tmp_path):
    store = Store(tmp_path)
    with patch('sinter.store.time.time', return_value=100):
        store.add_watch('Garden', 'garden', 3600)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: Store(tmp_path).claim(101), range(2)))
    assert sum(item is not None for item in results) == 1
    assert store.claim(200) is None
    assert store.claim(402) is not None


def test_watch_changes_retries_and_pause_preserve_results(tmp_path):
    store = Store(tmp_path)
    with patch('sinter.store.time.time', return_value=100):
        identifier = store.add_watch('Garden', 'garden', 3600, '2026-09-30')
    first = client.SearchResponse('t1', [client.SearchResult('A', 'https://example.org/a', 'first'), client.SearchResult('B', 'https://example.org/b', 'second')])
    assert store.run_due(101, lambda _: first) == 1
    second = client.SearchResponse('t2', [client.SearchResult('A', 'https://example.org/a', 'changed')])
    assert store.run_due(3702, lambda _: second) == 1
    saved = store.watches()[0]['results']
    assert saved['changed'] == ['https://example.org/a'] and saved['not_returned'] == ['https://example.org/b']
    def failure(_): raise client.APIError('Fixture failure')
    store.run_due(7303, failure)
    watch = store.watches()[0]
    assert watch['results'] == saved and watch['failures'] == 1 and watch['next_run'] == 7603
    store.change_watch(identifier, False)
    assert store.run_due(10000, failure) == 0
    store.change_watch(identifier, True)
    store.run_due(10001, lambda _: second)
    assert store.watches()[0]['failures'] == 0


def test_pausing_watch_during_search_discards_inflight_update(tmp_path):
    store = Store(tmp_path)
    with patch('sinter.store.time.time', return_value=100):
        identifier = store.add_watch('Garden', 'garden', 3600)
    def search(_):
        store.change_watch(identifier, False)
        return client.SearchResponse('now', [])
    store.run_due(101, search)
    assert store.watches()[0]['last_run'] is None


def test_calendar_unicode_folding_and_injection_safe(tmp_path):
    store = Store(tmp_path)
    store.add_watch('Garden ' + '\u00e9' * 90 + '\nEND:VEVENT', 'garden', 86400, '2026-09-30')
    output = calendar(store.watches())
    assert output.count('\r\nEND:VEVENT\r\n') == 2
    assert 'DTEND;VALUE=DATE:20261001' in output
    assert all(len(line.encode('utf-8')) <= 75 for line in output.split('\r\n'))


def wait_job(jobs, identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = jobs.get(identifier)
        if result['status'] in {'done', 'failed', 'cancelled'}:
            return result
        time.sleep(.005)
    raise AssertionError('Job did not finish')


def test_job_results_survive_long_execution_and_expire_after_completion():
    jobs = Jobs()
    try:
        job = Job('long', created_at=1, completed_at=4000, status='done', result={'ok': True})
        jobs._jobs[job.id] = job
        with patch('sinter.jobs.time.time', return_value=4001):
            assert jobs.get('long')['result'] == {'ok': True}
        with patch('sinter.jobs.time.time', return_value=5801):
            with pytest.raises(KeyError): jobs.get('long')
    finally: jobs.close()


def test_jobs_cancel_cooperatively_and_return_explicit_errors():
    jobs, started, release = Jobs(), threading.Event(), threading.Event()
    try:
        def operation(progress):
            started.set(); release.wait(5); progress('checkpoint'); return {'bad': 'should not publish'}
        identifier = jobs.submit(operation); assert started.wait(3)
        jobs.cancel(identifier); release.set()
        cancelled = wait_job(jobs, identifier)
        assert cancelled['status'] == 'cancelled' and cancelled['result'] is None
        def fail(progress): raise ValueError('Fixture invalid input')
        failed = wait_job(jobs, jobs.submit(fail))
        assert failed['status'] == 'failed' and failed['error'] == 'Fixture invalid input'
    finally: release.set(); jobs.close()


@pytest.mark.parametrize('raw,expected', [
    (b'data: {"choices":[{"delta":{"content":"Hi"}}]}\r\n\r\ndata:[DONE]\r\n\r\n', 'Hi'),
    (b': comment\n\ndata: {"choices":[{"delta":{"content":"Hi"}}]}\n\ndata: [DONE]', 'Hi')])
def test_sse_frames_and_final_unclosed_frame(raw, expected):
    with patch.object(client, '_post_raw', return_value=io.BytesIO(raw)):
        assert ''.join(client.chat_stream([client.Message('user', 'hello')])) == expected


@pytest.mark.parametrize('raw', [b'data: not-json\n\n', b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n', b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n'])
def test_malformed_incomplete_or_truncated_stream_raises(raw):
    with patch.object(client, '_post_raw', return_value=io.BytesIO(raw)), pytest.raises(client.APIError):
        list(client.chat_stream([client.Message('user', 'hello')]))


def test_zipapp_includes_assets_and_runs(tmp_path):
    root = Path(__file__).parents[1]
    sys.path.insert(0, str(root / 'tools'))
    from build_zipapp import build
    output = build(tmp_path / 'sinter.pyz')
    with zipfile.ZipFile(output) as archive:
        assert {'LICENSE', 'NOTICE', 'sinter/web/index.html', 'sinter/web/app.js'} <= set(archive.namelist())
        assert not any('__pycache__' in name for name in archive.namelist())
    result = subprocess.run([sys.executable, str(output), '--version'], capture_output=True, text=True, check=True)
    assert __version__ in result.stdout
    code = 'from importlib.resources import files; print(files("sinter").joinpath("web").joinpath("index.html").read_text(encoding="utf-8"))'
    env = __import__('os').environ.copy(); env['PYTHONPATH'] = str(output)
    page = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert '/static/app.js' in page.stdout
