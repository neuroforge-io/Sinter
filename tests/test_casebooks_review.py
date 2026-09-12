"""0.5 regressions for real community fragments, revisions, boundaries and recovery."""
import copy
import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import casebooks, client, review
from sinter.jobs import Jobs
from sinter.operations import Cancelled, DeadlineExceeded, budget, checkpoint
from sinter.store import Store


def project():
    return {'title': 'School evening', 'questions': 'Is the hall booking confirmed?\nInsurance excess?',
            'documents': [{'title': 'Early note', 'content': 'Hall booking discussed. It is not confirmed.'},
                          {'title': 'Later reply', 'content': 'Hall booking is provisional; ask before advertising.', 'date': '2026-09-01'}]}


def test_casebook_preserves_originals_negation_and_gap():
    book = project(); result = casebooks.build(book)
    assert result['question_index'][1]['status'] == 'no_wording_match'
    assert result['coverage']['exhaustive_review'] is False
    assert 'not confirmed' in result['markdown']
    assert 'provisional' in result['markdown']
    sources = {s['id']: s for s in result['sources']}
    for item in result['excerpts']:
        assert sources[item['source_id']]['content'][item['start']:item['end']] == item['quote']
    assert book == project()


@pytest.mark.parametrize('kind', ['brief', 'enquiry', 'agenda', 'handover'])
def test_document_formats_are_source_only(kind):
    with patch('sinter.client.chat', side_effect=AssertionError('No network')):
        result = casebooks.build(project(), kind)
    assert result['document_type'] == kind and result['source_register']
    assert 'DRAFT' in result['markdown']


@pytest.mark.parametrize('change', [
    {'documents': []}, {'documents': [None]}, {'title': []}, {'schema': 'other'},
    {'questions': '\n'.join(str(i) for i in range(21))},
    {'documents': [{'title': 'x', 'content': 'x\0y'}]},
    {'documents': [{'title': 'x', 'content': 'y', 'date': '2026-02-30'}]},
    {'documents': [{'title': 'x', 'content': 'y', 'url': 'javascript:alert(1)'}]},
    {'documents': [{'title': 'x', 'content': 'y' * 200001}]},
])
def test_casebook_rejects_bad_input(change):
    with pytest.raises(ValueError): casebooks.validate({**project(), **change})


def test_casebook_dedup_fingerprint_and_limits():
    book = project(); normalized = casebooks.validate(book)
    assert normalized == casebooks.validate(normalized)
    book['documents'].append(book['documents'][0])
    assert len(casebooks.validate(book)['documents']) == 2
    with pytest.raises(ValueError): casebooks.validate({**book, 'documents': book['documents'] * 101})


def test_large_fragmented_material_keeps_last_passage():
    content = 'Background without useful details.\n' * 5000 + 'The unique insurance excess is not confirmed.'
    book = {'title': 'Planning', 'questions': 'unique insurance excess', 'documents': [{'title': 'Policy', 'content': content}]}
    result = casebooks.build(book)
    assert any('unique insurance' in item['quote'] for item in result['excerpts'])
    assert result['coverage']['characters_supplied'] == len(content)


def test_revision_conflict_preserves_both_inputs(tmp_path):
    repository = casebooks.Casebooks(Store(tmp_path))
    original = repository.save(project()); edited = project(); edited['title'] = 'Edited'
    saved = repository.save(edited, original['id'], original['revision'])
    with pytest.raises(ValueError, match='another window'): repository.save(project(), original['id'], original['revision'])
    with pytest.raises(ValueError): repository.delete(original['id'], original['revision'])
    assert repository.get(saved['id'])['document']['title'] == 'Edited'
    assert len(repository.list()) == 1
    reopened = casebooks.Casebooks(Store(tmp_path)); assert reopened.get(saved['id'])['revision'] == 2
    reopened.delete(saved['id'], 2); assert reopened.list() == []


def test_draft_requires_consent_and_known_citations():
    report = casebooks.build(project())
    with patch('sinter.client.chat') as model:
        with pytest.raises(ValueError): casebooks.draft(report, False)
        model.assert_not_called()
    for bad in ('No citations', '[Eabc123] Hall is approved.'):
        with patch('sinter.client.chat', return_value=client.ChatResult(bad)):
            with pytest.raises(client.APIError): casebooks.draft(report, True)
    identity = report['excerpts'][0]['id']
    with patch('sinter.client.chat', return_value=client.ChatResult('Please clarify [' + identity + ']')):
        draft = casebooks.draft(report, True)
    assert draft['model_draft'] and not report.get('model_draft')
    assert 'UNVERIFIED' in draft['markdown'] and draft['excerpts'] == report['excerpts']


def test_review_resume_and_failure_keep_completed_work():
    book = {'title': 'Large source', 'documents': [{'title': 'Policy', 'content': 'A' * 19000}]}
    checkpoints = []
    substantive = 'no issues found after checking the supplied material.'
    with patch('sinter.client.chat', side_effect=[client.ChatResult('Unverified first review: ' + substantive),
                                                  client.APIError('timeout', 504)]) as model:
        first = review.run(book, on_checkpoint=lambda value: checkpoints.append(copy.deepcopy(value)))
    assert model.call_count == 2
    assert first['coverage']['batches_complete'] == 1
    assert first['coverage']['batches_failed'] == 0
    assert first['coverage']['batches_uncertain'] == 1
    assert len(checkpoints) == 4
    assert checkpoints[0]['batches'][0]['status'] == 'running'
    assert checkpoints[1]['batches'][0]['status'] == 'done'
    with patch('sinter.client.chat', return_value=client.ChatResult('Remaining review: ' + substantive)) as model:
        second = review.run(book, resume=first)
    assert model.call_count == 2 and second['coverage']['batches_complete'] == 3
    assert second['coverage']['batches_uncertain'] == 1
    with patch('sinter.client.chat', return_value=client.ChatResult('Explicit retry: ' + substantive)) as model:
        third = review.run(book, resume=second, retry_uncertain=True)
    assert model.call_count == 1 and third['coverage']['batches_complete'] == 4
    assert 'Unverified first review' in third['markdown']
    assert third['coverage']['batches_partial'] == 0
    assert third['coverage']['whole_collection_verified'] is False


def test_review_offline_no_network_and_checkpoint_binding():
    with patch('sinter.client.chat', side_effect=AssertionError('offline')):
        first = review.run(project(), offline=True)
    assert first['coverage']['requests_this_run'] == 0
    with pytest.raises(ValueError, match='different inputs'):
        review.run({**project(), 'title': 'Changed'}, resume=first)
    with pytest.raises(ValueError): review.run(project(), max_parts=True)


def test_review_file_admission_and_atomic_checkpoint(tmp_path):
    (tmp_path / 'note.md').write_text('A community note.', encoding='utf-8')
    (tmp_path / '.env').write_text('not for the model')
    (tmp_path / 'credentials.json').write_text('{}')
    (tmp_path / 'photo.jpg').write_bytes(b'nottext\0')
    (tmp_path / 'node_modules').mkdir(); (tmp_path / 'node_modules' / 'junk.js').write_text('unrelated')
    payload, ledger = review.load_collection(tmp_path)
    assert [doc['title'] for doc in payload['documents']] == ['note.md']
    assert len(ledger['skipped']) == 3
    target = tmp_path / 'checkpoint.json'; review.atomic_save(target, {'n': 1}); review.atomic_save(target, {'n': 2})
    assert json.loads(target.read_text()) == {'n': 2}
    assert not list(tmp_path.glob('.sinter-review-*'))


def test_operation_cancel_and_expired_budget():
    cancel = threading.Event()
    with budget(10, cancel):
        cancel.set()
        with pytest.raises(Cancelled): checkpoint()
    with patch('sinter.operations.time.monotonic', side_effect=[0, 0, 11]):
        with budget(10):
            with pytest.raises(DeadlineExceeded): checkpoint()


def test_jobs_are_recoverable_without_leaking_results_into_list():
    jobs = Jobs()
    try:
        identifier = jobs.submit(lambda progress: {'private': 'test data'}, label='Review')
        end = time.monotonic() + 3
        while jobs.get(identifier)['status'] != 'done' and time.monotonic() < end: time.sleep(.01)
        assert jobs.get(identifier)['result']['private'] == 'test data'
        listing = jobs.list(); assert listing[0]['label'] == 'Review'
        assert 'result' not in listing[0] and 'test data' not in str(listing)
    finally: jobs.close()


def test_read_timeouts_keep_json_longer_than_stream_idle():
    class Socket:
        def settimeout(self, value): self.timeout = value
    sock = Socket()
    class Response: pass
    response = Response(); response.fp = Response(); response.fp.raw = Response(); response.fp.raw._sock = sock
    with patch('sinter.client.time.monotonic', return_value=0):
        client._read_timeout(response, 120, 120)
    assert sock.timeout == 120


def test_drip_feed_cannot_extend_json_wall_budget():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            try:
                for value in b'{"data":[]}' * 10:
                    self.wfile.write(bytes([value])); self.wfile.flush(); time.sleep(.025)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    start = time.monotonic()
    try:
        with client.connection_settings({'api_url': f'http://127.0.0.1:{server.server_port}', 'model': 'fixture', 'api_key': ''}):
            with patch.object(client, 'CONTROL_TIMEOUT', .12):
                with pytest.raises(client.APIError): client._get('/models')
        assert time.monotonic() - start < 1.5
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_casebook_http_round_trip_and_stale_draft(tmp_path):
    import urllib.request
    from urllib.error import HTTPError
    from sinter.server import make_server
    server = make_server(port=0, directory=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, token=True):
        headers = {'Content-Type': 'application/json'}
        if token: headers['X-Sinter-Token'] = server.app.token
        req = urllib.request.Request(base + path, headers=headers, data=json.dumps(data).encode() if data else None)
        with urllib.request.urlopen(req, timeout=3) as response: return json.load(response)
    try:
        with pytest.raises(HTTPError) as blocked:
            request('/api/casebooks/save', {'document': project()}, token=False)
        assert blocked.value.code == 403
        saved = request('/api/casebooks/save', {'document': project()})
        assert len(request('/api/casebooks')['casebooks']) == 1
        with pytest.raises(HTTPError):
            request('/api/casebooks/draft', {'id': saved['id'], 'revision': 1, 'consent': True, 'fingerprint': 'not-previewed'})
        job = request('/api/casebooks/build', {'id': saved['id'], 'revision': 1})
        for _ in range(100):
            result = request('/api/jobs/' + job['id'])
            if result['status'] in {'done', 'failed'}: break
            time.sleep(.01)
        assert result['status'] == 'done' and result['result']['coverage']['documents_supplied'] == 2
        assert request('/api/jobs')['jobs'][0]['label'].startswith('Casebook:')
    finally:
        server.shutdown(); server.app.close(); server.server_close(); thread.join(timeout=2)
